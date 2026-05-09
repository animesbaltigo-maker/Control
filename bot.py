from __future__ import annotations

import asyncio
import base64
import html
import re
from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from control_client import ControlClient
from control_config import BotTarget, bot_token, load_targets, owner_ids


OWNER_IDS = owner_ids()
OWNER_ID = min(OWNER_IDS) if OWNER_IDS else 0
TARGETS = load_targets()
CLIENT = ControlClient()


@dataclass
class BroadcastDraft:
    selected: set[str] = field(default_factory=lambda: {target.id for target in TARGETS})
    step: str = ""
    text: str = ""
    button_rows: list[list[dict[str, str]]] = field(default_factory=list)
    media: dict[str, str] | None = None
    pin: bool = False


DRAFTS: dict[int, BroadcastDraft] = {}


def is_owner(user_id: int | None) -> bool:
    return bool(user_id and user_id in OWNER_IDS)


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def target_by_id(target_id: str) -> BotTarget | None:
    for target in TARGETS:
        if target.id == target_id:
            return target
    return None


def draft_for(user_id: int) -> BroadcastDraft:
    draft = DRAFTS.get(user_id)
    if draft is None:
        draft = BroadcastDraft()
        DRAFTS[user_id] = draft
    return draft


def parse_buttons(raw: str) -> tuple[list[list[dict[str, str]]], str | None]:
    rows: list[list[dict[str, str]]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        row: list[dict[str, str]] = []
        for part in re.split(r"\s+&&\s+", line):
            match = re.match(r"^(.+?)\s+-\s+(.+)$", part.strip())
            if not match:
                return [], "Use: Texto do botão - link"
            text = match.group(1).strip()[:64]
            value = match.group(2).strip()
            if value.startswith("t.me/"):
                value = "https://" + value
            if not value.startswith(("http://", "https://", "tg://")):
                return [], "O link precisa começar com http://, https://, tg:// ou t.me/"
            row.append({"type": "url", "text": text, "value": value})
        rows.append(row)
    return rows, None


async def media_payload(message: Message) -> dict[str, str] | None:
    media_type = ""
    file = None
    filename = "broadcast.bin"
    if message.photo:
        media_type = "photo"
        file = await message.photo[-1].get_file()
        filename = "photo.jpg"
    elif message.video:
        media_type = "video"
        file = await message.video.get_file()
        filename = message.video.file_name or "video.mp4"
    elif message.animation:
        media_type = "animation"
        file = await message.animation.get_file()
        filename = message.animation.file_name or "animation.gif"
    elif message.audio:
        media_type = "audio"
        file = await message.audio.get_file()
        filename = message.audio.file_name or "audio.mp3"
    elif message.document:
        media_type = "document"
        file = await message.document.get_file()
        filename = message.document.file_name or "document.bin"
    if not file:
        return None
    raw = await file.download_as_bytearray()
    return {"type": media_type, "filename": filename, "data": base64.b64encode(bytes(raw)).decode("ascii")}


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Métricas", callback_data="ctl|metrics")],
            [InlineKeyboardButton("📢 Broadcast global", callback_data="ctl|broadcast")],
            [InlineKeyboardButton("🟢 Status dos bots", callback_data="ctl|status")],
        ]
    )


def broadcast_keyboard(draft: BroadcastDraft) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🌍 Destino", callback_data="bc|dest")],
            [InlineKeyboardButton("🖼️ Mídia", callback_data="bc|media"), InlineKeyboardButton("👀 Ver", callback_data="bc|view_media")],
            [InlineKeyboardButton("🔠 Texto", callback_data="bc|text"), InlineKeyboardButton("👀 Ver", callback_data="bc|view_text")],
            [InlineKeyboardButton("⌨️ Botões", callback_data="bc|buttons"), InlineKeyboardButton("👀 Ver", callback_data="bc|view_buttons")],
            [InlineKeyboardButton("📌 Fixar", callback_data="bc|pin"), InlineKeyboardButton("✅ Sim" if draft.pin else "❌ Não", callback_data="bc|pin")],
            [InlineKeyboardButton("👀 Visualização completa", callback_data="bc|preview")],
            [InlineKeyboardButton("Próximo ➡️", callback_data="bc|next")],
            [InlineKeyboardButton("❌ Fechar", callback_data="bc|close")],
        ]
    )


def target_keyboard(draft: BroadcastDraft) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("✅ Todos os bots" if len(draft.selected) == len(TARGETS) else "⬜ Todos os bots", callback_data="bc|all")]]
    for target in TARGETS:
        mark = "✅" if target.id in draft.selected else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {target.name}", callback_data=f"bc|toggle|{target.id}")])
    rows.append([InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")])
    return InlineKeyboardMarkup(rows)


def broadcast_text(draft: BroadcastDraft, note: str = "") -> str:
    selected = ", ".join(target.name for target in TARGETS if target.id in draft.selected) or "Nenhum"
    lines = [
        "📢 <b>Broadcast global</b>",
        "",
        f"<blockquote>🌍 <b>Destino:</b> {esc(selected)}",
        f"🖼️ <b>Mídia:</b> {'Sim' if draft.media else 'Não'}",
        f"🔠 <b>Texto:</b> {'Sim' if draft.text else 'Não'}",
        f"⌨️ <b>Botões:</b> {sum(len(row) for row in draft.button_rows)}",
        f"📌 <b>Fixar:</b> {'Sim' if draft.pin else 'Não'}</blockquote>",
    ]
    if note:
        lines.extend(["", f"<blockquote>{esc(note)}</blockquote>"])
    lines.extend(["", "<i>Escolha uma opção abaixo.</i>"])
    return "\n".join(lines)


def config_summary() -> str:
    owner_list = ", ".join(str(item) for item in sorted(OWNER_IDS)) or "nao configurado"
    target_lines = "\n".join(
        f"• <b>{esc(target.name)}</b> <code>{esc(target.base_url)}</code>"
        for target in TARGETS
    ) or "Nenhum bot em CONTROL_BOTS."
    return (
        "⚙️ <b>Diagnostico do Control</b>\n\n"
        f"<blockquote>• <b>Owners:</b> <code>{esc(owner_list)}</code>\n"
        f"• <b>Bots configurados:</b> {len(TARGETS)}</blockquote>\n\n"
        f"{target_lines}"
    )


async def require_owner(update: Update) -> bool:
    user = update.effective_user
    if is_owner(user.id if user else None):
        return True
    message = update.effective_message
    if message:
        current_id = user.id if user else 0
        await message.reply_text(
            f"Acesso restrito.\n\nSeu ID: <code>{current_id}</code>\nConfigure esse ID em <code>OWNER_ID</code> no .env.",
            parse_mode=ParseMode.HTML,
        )
    return False


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.effective_message.reply_text(
        f"Seu ID: <code>{user.id if user else 0}</code>",
        parse_mode=ParseMode.HTML,
    )


async def central(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    await update.effective_message.reply_text(
        "🧠 <b>Central dos Bots</b>\n\nEscolha uma opção:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


def normalize_period(args: list[str]) -> str:
    return (args[0] if args else "total").strip().lower() or "total"


def premium_lines(result: dict[str, Any]) -> list[str]:
    premium = result.get("premium")
    if not isinstance(premium, dict) or not premium.get("available"):
        return []
    lines = [
        f"• <b>Premium ativo:</b> {int(premium.get('active_total') or 0)}",
        f"• <b>Registros de planos:</b> {int(premium.get('total_records') or 0)}",
    ]
    plans = premium.get("plans")
    if isinstance(plans, list):
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            name = esc(plan.get("name") or plan.get("code") or "Plano")
            active = int(plan.get("active") or 0)
            total = int(plan.get("total") or 0)
            lines.append(f"  - <b>{name}:</b> {active} ativos / {total} registros")
    return lines


def signed_number(value: Any) -> str:
    if value is None:
        return "sem histórico"
    number = int(value or 0)
    return f"+{number}" if number > 0 else str(number)


def channel_lines(result: dict[str, Any]) -> list[str]:
    channel = result.get("channel")
    if not isinstance(channel, dict):
        return []
    if not channel.get("available"):
        error = channel.get("error")
        username = channel.get("username")
        if error and username:
            return [f"• <b>Canal:</b> {esc(username)}", f"  - <b>Erro:</b> <code>{esc(error)}</code>"]
        return []
    username = channel.get("username")
    title = esc(channel.get("title") or username or "Canal")
    subscribers = int(channel.get("subscribers") or 0)
    deltas = channel.get("deltas") if isinstance(channel.get("deltas"), dict) else {}
    handle = f"@{esc(username)}" if username else ""
    return [
        f"• <b>Canal:</b> {title} {handle}".strip(),
        f"  - <b>Inscritos:</b> {subscribers:,}".replace(",", "."),
        f"  - <b>Crescimento:</b> 24h {signed_number(deltas.get('24h'))} • 7d {signed_number(deltas.get('7d'))} • 30d {signed_number(deltas.get('30d'))}",
    ]


async def metrics_text(period: str) -> str:
    results = await asyncio.gather(*(CLIENT.metrics(target, period) for target in TARGETS))
    lines = [f"📊 <b>Estatísticas • Control</b>", ""]
    for result in results:
        name = esc(result.get("name") or result.get("bot_id"))
        if not result.get("ok"):
            error = esc(result.get("error") or f"HTTP {result.get('http_status')}" if result.get("http_status") else "sem resposta")
            lines.append(f"🤖 <b>{name}:</b>\n<blockquote>🔴 Offline\n• <b>Erro:</b> <code>{error}</code></blockquote>\n")
            continue
        details = [
            f"• <b>Usuários ativos:</b> {int(result.get('users_active') or 0)}",
            f"• <b>Usuários inativos:</b> {int(result.get('users_inactive') or 0)}",
            f"• <b>Usuários banidos:</b> {int(result.get('users_banned') or 0)}",
            f"• <b>Administradores:</b> {int(result.get('admins') or 0)}",
        ]
        details.extend(premium_lines(result))
        details.extend(channel_lines(result))
        lines.append(f"🤖 <b>{name}:</b>\n<blockquote>{chr(10).join(details)}</blockquote>\n")
    return "\n".join(lines)


async def health_text() -> str:
    results = await asyncio.gather(*(CLIENT.health(target) for target in TARGETS))
    lines = ["🟢 <b>Status dos bots</b>", ""]
    for result in results:
        name = esc(result.get("name") or result.get("bot_id"))
        if result.get("ok"):
            uptime = int(result.get("uptime_seconds") or 0)
            lines.append(f"🟢 <b>{name}</b>\n<blockquote>online • uptime {uptime}s</blockquote>")
        else:
            error = esc(result.get("error") or f"HTTP {result.get('http_status')}" if result.get("http_status") else "sem resposta")
            lines.append(f"🔴 <b>{name}</b>\n<blockquote><code>{error}</code></blockquote>")
    return "\n\n".join(lines)


async def metricas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    await update.effective_message.reply_text(await metrics_text(normalize_period(context.args or [])), parse_mode=ParseMode.HTML)


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    await update.effective_message.reply_text(await health_text(), parse_mode=ParseMode.HTML)


async def diagnostico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    await update.effective_message.reply_text(config_summary(), parse_mode=ParseMode.HTML)


async def block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Use: <code>/block 1852596083</code>", parse_mode=ParseMode.HTML)
        return
    raw = context.args[0].strip()
    if raw.startswith("@"):
        await update.effective_message.reply_text("Por enquanto use o ID numérico. Username pode mudar e só será resolvido quando estiver salvo nos bots.")
        return
    if not raw.isdigit():
        await update.effective_message.reply_text("ID inválido.")
        return
    user_id = int(raw)
    results = await asyncio.gather(*(CLIENT.block(target, user_id, actor_id=OWNER_ID) for target in TARGETS))
    ok = sum(1 for item in results if item.get("ok"))
    await update.effective_message.reply_text(f"🚫 Usuário <code>{user_id}</code> bloqueado em <b>{ok}/{len(TARGETS)}</b> bots.", parse_mode=ParseMode.HTML)


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_owner(update):
        return
    draft = BroadcastDraft()
    DRAFTS[OWNER_ID] = draft
    await update.effective_message.reply_text(broadcast_text(draft), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_owner(query.from_user.id):
        return
    await query.answer()
    data = query.data or ""
    if data == "ctl|metrics":
        await query.edit_message_text(await metrics_text("total"), parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        return
    if data == "ctl|status":
        await query.edit_message_text(await health_text(), parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        return
    if data == "ctl|broadcast":
        draft = BroadcastDraft()
        DRAFTS[OWNER_ID] = draft
        await query.edit_message_text(broadcast_text(draft), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))
        return

    draft = draft_for(OWNER_ID)
    parts = data.split("|")
    action = parts[1] if len(parts) > 1 else ""
    if action == "close":
        await query.edit_message_text("Fechado.")
    elif action == "menu":
        draft.step = ""
        await query.edit_message_text(broadcast_text(draft), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))
    elif action == "dest":
        draft.step = ""
        await query.edit_message_text("🌍 <b>Escolha os bots</b>", parse_mode=ParseMode.HTML, reply_markup=target_keyboard(draft))
    elif action == "all":
        draft.selected = {target.id for target in TARGETS} if len(draft.selected) != len(TARGETS) else set()
        await query.edit_message_reply_markup(reply_markup=target_keyboard(draft))
    elif action == "toggle" and len(parts) >= 3:
        target_id = parts[2]
        if target_id in draft.selected:
            draft.selected.remove(target_id)
        else:
            draft.selected.add(target_id)
        await query.edit_message_reply_markup(reply_markup=target_keyboard(draft))
    elif action == "media":
        draft.step = "media"
        await query.edit_message_text("🖼️ <b>Envie a mídia da publicação.</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action == "text":
        draft.step = "text"
        await query.edit_message_text("🔠 <b>Envie o texto da publicação.</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action == "buttons":
        draft.step = "buttons"
        await query.edit_message_text("⌨️ <b>Envie os botões:</b>\n\n<blockquote>Site - https://site.com && Canal - t.me/canal</blockquote>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action == "pin":
        draft.pin = not draft.pin
        await query.edit_message_text(broadcast_text(draft), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))
    elif action == "view_media":
        await query.edit_message_text("🖼️ <b>Mídia</b>\n\n<blockquote>" + ("Configurada." if draft.media else "Nenhuma mídia.") + "</blockquote>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action == "view_text":
        await query.edit_message_text("🔠 <b>Texto</b>\n\n<blockquote>" + (draft.text or "Nenhum texto.") + "</blockquote>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action == "view_buttons":
        await query.edit_message_text("⌨️ <b>Botões</b>\n\n<blockquote>" + esc(str(draft.button_rows or "Nenhum botão.")) + "</blockquote>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="bc|menu")]]))
    elif action in {"preview", "next"}:
        if not draft.selected:
            await query.answer("Selecione pelo menos um bot.", show_alert=True)
            return
        if not draft.text and not draft.media:
            await query.answer("Defina texto ou mídia.", show_alert=True)
            return
        if draft.media:
            await query.message.reply_text("✅ Prévia com mídia configurada. Confira texto e botões abaixo.", parse_mode=ParseMode.HTML)
        await query.message.reply_text(draft.text or "📢", parse_mode=ParseMode.HTML)
        if action == "next":
            await query.edit_message_text("📬 <b>Confirmar broadcast global?</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="bc|menu"), InlineKeyboardButton("✅ Confirmar", callback_data="bc|confirm")]]))
    elif action == "confirm":
        payload = {"text": draft.text, "button_rows": draft.button_rows, "media": draft.media, "pin": draft.pin}
        selected = [target for target in TARGETS if target.id in draft.selected]
        results = await asyncio.gather(*(CLIENT.broadcast(target, payload) for target in selected))
        ok = sum(1 for item in results if item.get("ok"))
        await query.edit_message_text(f"🚀 Broadcast iniciado em <b>{ok}/{len(selected)}</b> bots selecionados.", parse_mode=ParseMode.HTML)


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update.effective_user.id if update.effective_user else None):
        return
    draft = draft_for(OWNER_ID)
    message = update.effective_message
    if not message or not draft.step:
        return
    if draft.step == "text":
        draft.text = message.text_html or message.caption_html or esc(message.text or message.caption or "")
        draft.step = ""
        await message.reply_text(broadcast_text(draft, "Texto salvo."), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))
    elif draft.step == "buttons":
        rows, error = parse_buttons(message.text or "")
        if error:
            await message.reply_text(error)
            return
        draft.button_rows = rows
        draft.step = ""
        await message.reply_text(broadcast_text(draft, "Botões salvos."), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))
    elif draft.step == "media":
        media = await media_payload(message)
        if not media:
            await message.reply_text("Envie foto, vídeo, GIF, áudio ou arquivo.")
            return
        draft.media = media
        draft.step = ""
        await message.reply_text(broadcast_text(draft, "Mídia salva."), parse_mode=ParseMode.HTML, reply_markup=broadcast_keyboard(draft))


def main() -> None:
    token = bot_token()
    if not token:
        raise RuntimeError("Configure BOT_TOKEN.")
    if not TARGETS:
        print("AVISO: nenhum bot configurado em CONTROL_BOTS.", flush=True)
    print(f"Control iniciado com {len(TARGETS)} bots e owners {sorted(OWNER_IDS)}.", flush=True)
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler(["start", "central"], central))
    app.add_handler(CommandHandler(["status", "diagnostico"], diagnostico))
    app.add_handler(CommandHandler(["metricas", "metrics"], metricas))
    app.add_handler(CommandHandler(["health", "saude"], health))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(callbacks, pattern=r"^(ctl|bc)\|"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_router), group=20)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

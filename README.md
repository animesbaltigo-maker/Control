# Control Baltigo

Bot central para administrar os bots Baltigo pelo Telegram.

## Comandos

- `/central` abre o painel.
- `/id` mostra seu ID do Telegram para configurar o dono.
- `/status` ou `/diagnostico` mostra owners e bots configurados.
- `/metricas` mostra estatisticas globais.
- `/broadcast` monta uma campanha global com selecao de bots.
- `/block 1852596083` bloqueia um usuario em todos os bots conectados.

## Como ligar na VPS

Clone e instale:

```bash
git clone https://github.com/animesbaltigo-maker/Control.git control
cd control
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

No `.env`, preencha:

```env
BOT_TOKEN=token_do_bot_control
OWNER_ID=1852596083
CONTROL_SECRET=o_mesmo_segredo_em_todos
```

O `CONTROL_BOTS` ja vem com as portas sugeridas:

```text
animes 8781
mangas 8782
hqs 8783
novels 8784
series 8785
radio 8786
baixaaqui 8787
source 8788
```

Em cada bot controlado, use o mesmo `CONTROL_SECRET` e uma porta unica:

```env
CONTROL_AGENT_ENABLED=1
CONTROL_SECRET=o_mesmo_segredo_em_todos
CONTROL_AGENT_HOST=127.0.0.1
CONTROL_AGENT_PORT=8782
CONTROL_BOT_ID=mangas
CONTROL_BOT_NAME=MangasBaltigo_Bot
```

Depois reinicie cada bot controlado e rode o Control:

```bash
source venv/bin/activate
python bot.py
```

Se o Control e os bots estao na mesma VPS, mantenha `http://127.0.0.1:PORTA`.

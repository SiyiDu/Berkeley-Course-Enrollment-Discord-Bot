# Berkeley Course Enrollment Bot

Discord bot that manages UC Berkeley course enrollment, registration, and private discussion threads inside a server. Features include:

- Slash commands to register students, enroll/drop classes, and manage server state
- Panel-based UI with persistent buttons, selects, and modals for bulk enrollment
- Automatic student role provisioning and optional private department containers
- JSON-backed storage for course indices, enrollments, and registered users

## Project Layout

```
.
├── berkeley_bot/
│   ├── bot.py               # Bot factory and dependency wiring
│   ├── commands.py          # Slash command definitions
│   ├── config.py            # Environment & path configuration
│   ├── courses.py           # Course metadata helpers (terms, slugs, etc.)
│   ├── enrollment.py        # Enrollment service logic
│   ├── permissions.py       # App command guards
│   ├── registration.py      # Student registration validation/role handling
│   ├── state.py             # Mutable runtime state (current term)
│   ├── storage.py           # JSON persistence layer
│   └── views.py             # Discord UI components (buttons, modals, selects)
├── course_index.json        # Thread/container IDs keyed by course slug
├── enrollments.json         # User → course slug lists
├── users.json               # Registered student records
├── main.py                  # Simple entrypoint
├── requirements.txt
└── .env                     # Secrets (not checked in)
```

## Configuration

Populate `.env` with your bot token and optionally override defaults:

```
DISCORD_TOKEN=your_token_here
GUILD_ID=1432284673865682959       # Server ID
STUDENT_ROLE_NAME=student
BERKELEY_SUFFIX=@berkeley.edu
DEFAULT_TERM=fa25
PRIVATE_CONTAINERS=true            # Toggle per-department private channels
```

JSON storage files will be created automatically if missing.

## Installation

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Running the Bot

```bash
python main.py
```

On startup the bot syncs slash commands to the configured guild, logs readiness, and waits for interactions.

## GitHub Deployment Tips

1. Commit the project (excluding `.env` and other secrets).
2. Push to a GitHub repository that mirrors your Discord deployment.
3. Configure GitHub Secrets (if using CI/CD) with bot token values.
4. Optionally set up a workflow that deploys the bot to a hosting provider (Heroku, Railway, etc.) using the launch command above.


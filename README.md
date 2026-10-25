# SwapShelf

Campus buy/sell board. Post a listing, filter the public board by category, message the seller, and mark your own listing sold.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver 0.0.0.0:3000
```

Open http://localhost:3000. The database file is `data/swapshelf.db`.

`migrate` also loads the demo rows (the market app seeds after its migration). `seed` is safe to run again.

## Docker

```bash
docker compose up --build
```

The app listens on port 3000.

## Demo accounts

Sign in with the username, not the email.

| Username | Password | What is on the board |
| --- | --- | --- |
| alex | campus123 | 67W USB-C charger and a blue campus bike |
| jordan | campus123 | CPEG 470 textbook, and a message thread on Alex's bike |
| sam | foundit! | Brass desk lamp, already sold |

## Tests

```bash
python manage.py test
```

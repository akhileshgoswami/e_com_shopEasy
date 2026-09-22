# Admin Panel Access

## 1. Start the app

```bash
cd /Users/akhileshgoswami/Documents/project_latest/e-com
./projectrun.sh          # or: docker compose up -d db web
```

## 2. Create an admin user (one-time)

```bash
docker compose exec web flask seed-admin --email admin@example.com
```

- Prompts for a password (min 8 characters, asks twice to confirm).
- Running it again with the same email **promotes/resets** that user to admin — safe to re-run if you forget the password.
- Non-interactive (e.g. scripts/CI): `docker compose exec web flask seed-admin --email admin@example.com --password "YourStrongPass123!"`

Without Docker (venv):

```bash
source .venv/bin/activate
export FLASK_APP=wsgi.py
flask seed-admin --email admin@example.com
```

## 3. Log in

| Environment | Admin login URL |
|---|---|
| Docker (`projectrun.sh` / `docker compose`) | http://localhost:8000/admin/login |
| Local venv (`flask run`) | http://localhost:5000/admin/login |
| Production | `https://<your-domain>/admin/login` |

Enter the email/password from step 2 → redirects to `/admin/dashboard`.

## Notes

- Admin login is a **separate route** (`/admin/login`) from the customer login (`/login`) — a customer account, even a valid one, gets "This account does not have admin access" if it tries here.
- "Sign in with Google" accounts are always created as `customer` role — Google login **cannot** be used for admin access. Only `flask seed-admin` creates/promotes admins.
- 5 wrong password attempts locks that account for 15 minutes (applies to admin accounts too).
- To promote an existing customer account to admin instead of creating a new one, just run `flask seed-admin --email <their email>` — it detects the existing user and switches their role.
- To demote/manage admins after the fact, log in as an existing admin and go to **Admin panel → Users → Edit** (you can't remove your own admin role from there, to avoid locking yourself out).

## Troubleshooting

- **"This account does not have admin access"** — that email exists but isn't an admin. Run `flask seed-admin --email <email>` to promote it.
- **Forgot the admin password** — re-run `flask seed-admin --email <same email>` with a new password; it overwrites the password on the existing account.
- **`/admin/dashboard` redirects to `/admin/login`** — you're not logged in, or your session expired. Log in again.
- **`/admin/dashboard` returns 403 Forbidden** — you're logged in, but as a non-admin account. Log out and log in with the admin email, or promote your account as above.

4111 1111 1111 1111

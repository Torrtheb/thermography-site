# Backup & recovery

This doc covers backing up the database (Neon) and storing the encryption key so the business can recover from loss or disaster.

---

## 1. `FIELD_ENCRYPTION_KEY` — safe storage

The same key is used to encrypt:

- **Clients**: name, phone, email, notes  
- **Contact submissions**: name, email, phone, message  

**If the key is lost, this data cannot be decrypted.** Back it up as soon as you generate it.

### Where to store the key

1. **Password manager (recommended)**  
   Create a secure note or entry, e.g.  
   - Title: `Thermography site – FIELD_ENCRYPTION_KEY`  
   - Value: the full key (one line, no spaces)  
   Use a manager that syncs and is backed up (e.g. 1Password, Bitwarden, iCloud Keychain with recovery).

2. **Encrypted backup**  
   If you keep a backup of env vars or secrets in a file, store that file in an encrypted volume or only in a secure, access-controlled place (not in the repo, not in plain cloud storage).

3. **One copy offline**  
   Keep at least one copy in a safe place that doesn’t depend on the same account (e.g. printed and stored in a safe, or on a USB in a safe). Only the business owner (or delegated person) should have access.

### When you first set the key

```bash
# Generate (do this once)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Put the output into your password manager and into Railway (or your host) as `FIELD_ENCRYPTION_KEY`.
- Do not paste it into chat, email, or docs that are shared or backed up in plain form.

### If you ever rotate the key

Rotating the key means re-encrypting all existing rows with a new key (custom script or management command). Until that exists, treat the key as permanent and only back it up; avoid changing it unless necessary.

---

## 2. Neon PostgreSQL — backups

Neon holds all app data (pages, clients, contact submissions, etc.). Encrypted fields are stored as ciphertext; decryption needs `FIELD_ENCRYPTION_KEY` as above.

### What Neon provides (as of 2025)

- **Point-in-time recovery (PITR)** on paid plans: restore to any moment in the retention window.  
- **Branching**: you can create a branch from a project for a point-in-time copy (useful as an ad‑hoc backup or for testing).  
- **Free tier**: check [Neon docs](https://neon.tech/docs/introduction) for current backup/restore options; free tier may have limited retention or no PITR.

### Recommended practice

1. **Check Neon’s current backup and restore docs**  
   [Neon documentation](https://neon.tech/docs) → Backup & restore (or similar). Note retention and how to restore.

2. **Use branches for important moments**  
   Before a big change or deploy, create a Neon branch of the project. That gives you a restorable copy at that time.

3. **Export critical data periodically (optional)**  
   If you want an extra safety net, run a script or cron that:
   - Uses `pg_dump` (or Neon’s export if available) with your `DATABASE_URL`, and  
   - Writes the dump to encrypted, access-controlled storage.  
   Keep dumps encrypted and only in places the business controls.

4. **Know how to restore**  
   Document (for the owner or you):
   - How to create/restore from a Neon branch, or  
   - How to restore from a `pg_dump` (new Neon project + restore).  
   After restore, ensure `FIELD_ENCRYPTION_KEY` is the same as when the backup was taken, or decryption will fail.

---

## 3. Quick checklist

- [ ] `FIELD_ENCRYPTION_KEY` stored in a password manager (and optionally one offline copy).  
- [ ] Neon project backup/restore and retention understood and documented.  
- [ ] Before major changes, a Neon branch (or other backup) is created.  
- [ ] Only trusted people have access to the key and the Neon project.

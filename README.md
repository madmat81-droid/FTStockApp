# Stock App (Flask, 2 DB, gestione utenze con blocco/sblocco)

- DB utenti (`users.db`) separato da DB stock (`stock.db`)
- Ruoli: utilizzatore/admin
- Admin: crea/modifica/elimina utenti, **blocca/sblocca** accesso
- CRUD pezzi con audit (created/updated + user id)
- Vista admin per disponibilità per codice e per utente (raggruppamenti FINIS e dettaglio righe)

## Avvio rapido
```bash
pip install -r requirements.txt
set SECRET_KEY=qualcosa_random
set ADMIN_USER=admin
set ADMIN_PASS=superpassword
python app.py
```
(PowerShell: usare $env:VAR="...")

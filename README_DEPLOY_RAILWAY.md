# Deploy su Railway (gratis) con persistenza SQLite

Questa guida pubblica l'app Flask su Railway con **Volume persistente** per i database SQLite.

## File richiesti nella repo
- `app.py`
- `requirements.txt` (contiene anche `gunicorn`)
- `Procfile`
- (opzionale) `README.md`

## 1) Crea una repository GitHub e pubblica i file
Esempio rapido (PowerShell/CMD):
```bash
git init
git add .
git commit -m "Stock App - first deploy"
git branch -M main
git remote add origin https://github.com/<TUO-USER>/<NOME-REPO>.git
git push -u origin main
```

## 2) Crea il progetto su Railway
1. Vai su https://railway.app/ e fai login.
2. **New Project → Deploy from GitHub** e seleziona la tua repo.
3. Railway installerà i pacchetti da `requirements.txt` e userà il `Procfile`.

> Se non parte, controlla i **Logs** del servizio.

## 3) Aggiungi un Volume per la persistenza
1. Entra nel **Service** dell'app su Railway.
2. Sezione **Storage / Volumes** → **Create Volume**.
3. Monta il volume sul percorso **`/data`** (mount path).

## 4) Imposta le variabili d'ambiente (Variables)
Nella tab **Variables** del servizio, aggiungi:
- `USERS_DATABASE_URL=sqlite:////data/users.db`
- `STOCK_DATABASE_URL=sqlite:////data/stock.db`
- `SECRET_KEY=qualcosa_random`
- *(facoltativo, solo al primo avvio)* `ADMIN_USER=admin`
- *(facoltativo, solo al primo avvio)* `ADMIN_PASS=superpassword`

> Il path `/data` corrisponde al Volume persistente.

## 5) Deploy e dominio pubblico
- Se il deploy non riparte da solo, clicca **Deploy** o **Restart**.
- Vai in **Settings → Networking → Generate Domain** per ottenere l'URL pubblico HTTPS.

## 6) Primo accesso
- Apri l'URL.
- Se hai impostato `ADMIN_USER`/`ADMIN_PASS`, verrà creato l'utente admin al primo boot.
- In alternativa è disponibile l'admin di sviluppo `admin`/`admin` (cambialo subito da **Utenti**).

## 7) Verifiche utili
- **Logs**: se vedi errori tipo `ModuleNotFoundError` o 502, controlla i nomi file e il Procfile.
- **DB**: i file `users.db` e `stock.db` si creano automaticamente dentro `/data`.
- **Region**: puoi impostare la regione Railway (es. EU) per bassa latenza dall'Italia.

## 8) Aggiornamenti
- Commit & push su GitHub → Railway effettua il **redeploy**.
- I dati **restano** nel Volume.

## 9) Sicurezza minima
- Cambia `SECRET_KEY` in produzione.
- Usa password robuste per gli utenti.
- Valuta di disabilitare `debug=True` in `app.py` quando in produzione.

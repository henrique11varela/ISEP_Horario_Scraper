# asdasd

``` bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y chromium chromium-driver
chromium --version
chromedriver --version
which chromium
which chromedriver
sudo timedatectl set-ntp on
sudo timedatectl set-timezone Europe/Lisbon
```

## Docker

``` bash
cp .env.example .env   # then fill in your credentials and class ids
docker compose up -d --build
```

The app is served on port 5000 (set `PORT` in `.env` to change it) and the SQLite database is stored as `horario.db` in the project folder.

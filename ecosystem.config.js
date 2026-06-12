module.exports = {
  apps: [{
    name: "media-api",
    script: "gunicorn",
    args: "main:app -c gunicorn.conf.py",
    interpreter: "python3",
    env: { PYTHONUNBUFFERED: "1" },
    watch: false,
    autorestart: true,
    max_restarts: 10,
  }]
}

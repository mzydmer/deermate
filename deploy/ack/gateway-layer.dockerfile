# Appended to a generated Dockerfile from the pinned upstream by ack_deploy.py.
# The build context contains only an upstream Git archive and our built wheel.
COPY deermate-wheel/ /tmp/deermate-wheel/
RUN uv pip install --python /app/backend/.venv/bin/python \
      "$(find /tmp/deermate-wheel -name 'deermate-*.whl' -print -quit)[mcp,ssh]" \
    && /app/backend/.venv/bin/python -c 'import deermate,asyncssh; import deermate.mcp_server' \
    && rm -rf /tmp/deermate-wheel

# AsyncSSH/getpass need a real local identity even with an explicit remote user.
# Kubernetes runs this image as UID 1000; the upstream Python base has no such user.
RUN groupadd --gid 1000 deermate \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin deermate
ENV HOME=/home/deermate USER=deermate LOGNAME=deermate
USER 1000:1000

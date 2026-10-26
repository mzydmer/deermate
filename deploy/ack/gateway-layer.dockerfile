# Appended to the unchanged pinned upstream backend/Dockerfile by ack_deploy.py.
# The build context contains only an upstream Git archive and our built wheel.
COPY deermate-wheel/ /tmp/deermate-wheel/
RUN uv pip install --python /app/backend/.venv/bin/python \
      "$(find /tmp/deermate-wheel -name 'deermate-*.whl' -print -quit)[mcp,ssh]" \
    && /app/backend/.venv/bin/python -c 'import deermate,asyncssh; import deermate.mcp_server' \
    && rm -rf /tmp/deermate-wheel

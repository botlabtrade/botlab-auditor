# Sandbox image: the ONLY place uploaded strategy code runs in production.
#
# Build it from the repository root (the build context needs sandbox/runner.py):
#     docker build -f sandbox/Dockerfile -t botlab-sandbox:latest .
#
# The host never passes an entrypoint, so the arguments in sandbox/__init__.py::_run_docker
# (--mode / --input / --work / --out / --timeout) land straight on runner.py.
#
# Nothing in this image can be relied on as a security boundary on its own: the container flags the
# host applies (--network none, --read-only, --user 65534, --cap-drop ALL, --pids-limit,
# --memory, --cpus) are what actually contain the code. This image only keeps the attack surface
# small: a slim base, a non-root user, and exactly three third-party packages.
FROM python:3.12-slim

# honest_backtest is the open-source gate/statistics library this project was built on.
ARG HONEST_BACKTEST=honest_backtest @ git+https://github.com/botlabtrade/botlab-oss.git

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    HOME=/tmp

# Nothing beyond pandas, numpy and honest_backtest. No compilers, no curl, no git in the final image.
RUN pip install --no-cache-dir "pandas>=2.0" "numpy>=1.24" \
 && pip install --no-cache-dir "${HONEST_BACKTEST}" \
 && rm -rf /root/.cache /tmp/*

# The runner is the whole application: one standalone file, stdlib + the three packages above.
WORKDIR /app
COPY sandbox/runner.py /app/runner.py
RUN chmod 0444 /app/runner.py

# Matches --user 65534:65534 on the host side. Declared here too, so a hand-run container without
# that flag still starts unprivileged.
USER 65534:65534

ENTRYPOINT ["python", "/app/runner.py"]
CMD ["--mode", "signals", "--input", "/input", "--work", "/work", "--out", "/out"]

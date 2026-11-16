FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /opt/quantlab
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir '.[console,api,postgres,aws,stream]'
RUN groupadd -r quant && useradd --no-log-init -r -g quant -d /opt/quantlab quant
RUN mkdir -p /opt/quantlab/artifacts && chown -R quant:quant /opt/quantlab
USER quant
EXPOSE 8501
CMD ["streamlit","run","src/quantlab/console/app.py","--server.address=0.0.0.0","--server.port=8501","--server.headless=true"]

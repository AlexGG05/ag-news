FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py sources.py auth.py ui.py theme.js i18n.py translations.py ./
RUN useradd -r -u 10001 appuser
USER appuser
EXPOSE 8080
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080","--workers","1"]

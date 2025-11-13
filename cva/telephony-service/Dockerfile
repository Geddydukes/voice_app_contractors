FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    uvicorn[standard]==0.29.0
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code and tools (self-contained package)
COPY agent.py orchestrator.py system_prompt.txt ./
COPY tools/ ./tools/

EXPOSE 8080

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]

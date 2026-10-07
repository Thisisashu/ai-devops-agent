FROM python:3.12-slim

# Install Terraform
RUN apt-get update && apt-get install -y curl unzip git && \
    curl -fsSL https://releases.hashicorp.com/terraform/1.16.1/terraform_1.16.1_linux_amd64.zip -o tf.zip && \
    unzip tf.zip -d /usr/local/bin && rm tf.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "server.py"]

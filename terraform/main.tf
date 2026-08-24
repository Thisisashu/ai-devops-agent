terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}

resource "aws_s3_bucket" "data_bucket" {
  bucket = "ai-devops-agent-data-444083008248"

  tags = {
    Project     = "AI-DevOps-Agent"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}

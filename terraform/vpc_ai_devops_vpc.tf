resource "aws_vpc" "ai_devops_vpc" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name        = "ai-devops-vpc"
    Environment = "development"
  }
}
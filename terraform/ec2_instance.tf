resource "aws_instance" "new_instance" {
  ami                         = "ami-0c55b159819cm Example" # Replace with the appropriate AMI ID
  instance_type               = "t2.micro"
  subnet_id                   = "subnet-0c55b159819cm Example" # Replace with the appropriate subnet ID
  associate_public_ip_address = true
  tags = {
    Name        = "ai-devops-new-vm"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}
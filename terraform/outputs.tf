output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "security_group_id" {
  description = "EC2 security group ID"
  value       = aws_security_group.ec2.id
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.ubuntu.id
}

output "instance_public_ip" {
  description = "EC2 instance public IP address"
  value       = aws_instance.ubuntu.public_ip
}

output "instance_public_dns" {
  description = "EC2 instance public DNS"
  value       = aws_instance.ubuntu.public_dns
}

output "ami_id" {
  description = "Ubuntu 22.04 AMI used"
  value       = data.aws_ami.ubuntu_22_04.id
}

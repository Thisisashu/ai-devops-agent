resource "aws_s3_bucket" "example" {
  bucket = "example"
  region = "ap-south-1"

  tags = {
    Environment = "development"
    Name        = "example-bucket"
  }

  force_destroy = true
}
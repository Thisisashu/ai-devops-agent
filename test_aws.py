from tools.aws import (
    get_aws_account,
    list_s3_buckets,
    list_ec2_instances
)

print("AWS Account:")
print(get_aws_account())

print("\nS3 Buckets:")
print(list_s3_buckets())

print("\nEC2 Instances:")
print(list_ec2_instances())

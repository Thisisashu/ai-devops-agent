import boto3


def get_aws_account():

    sts = boto3.client("sts")

    response = sts.get_caller_identity()

    return {
        "account": response["Account"],
        "arn": response["Arn"],
        "user_id": response["UserId"]
    }


def list_s3_buckets():

    s3 = boto3.client("s3")

    response = s3.list_buckets()

    buckets = []

    for bucket in response["Buckets"]:
        buckets.append(bucket["Name"])

    return buckets


def list_ec2_instances():

    ec2 = boto3.client("ec2")

    response = ec2.describe_instances()

    instances = []

    for reservation in response["Reservations"]:

        for instance in reservation["Instances"]:

            instances.append({
                "id": instance["InstanceId"],
                "state": instance["State"]["Name"],
                "type": instance["InstanceType"]
            })

    return instances

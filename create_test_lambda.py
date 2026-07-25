#!/usr/bin/env python3

import io
import json
import time
import zipfile
import boto3
import botocore


ROLE_NAME = "YOUR_LAMBDA_ROLE_NAME"
REGION = "us-east-1"

LAMBDA_CODE = """
def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": "Hello from temporary Lambda!"
    }
"""


def build_zip():
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lambda_function.py", LAMBDA_CODE)

    buffer.seek(0)
    return buffer.read()


def main(account_id):

    session = assume_role(account_id)

    iam = session.client("iam")
    lambda_client = session.client("lambda", region_name=REGION)
    logs = session.client("logs", region_name=REGION)

    #
    # Get role ARN
    #
    role = iam.get_role(RoleName=ROLE_NAME)["Role"]

    role_arn = role["Arn"]

    function_name = f"lambda-lastused-test-{int(time.time())}"

    print(f"Creating Lambda: {function_name}")

    response = lambda_client.create_function(
        FunctionName=function_name,
        Runtime="python3.13",
        Role=role_arn,
        Handler="lambda_function.lambda_handler",
        Code={
            "ZipFile": build_zip()
        },
        Timeout=10,
        MemorySize=128,
        Publish=True,
    )

    print(f"Function ARN : {response['FunctionArn']}")

    #
    # Wait until active
    #
    print("Waiting for Lambda to become Active...")

    waiter = lambda_client.get_waiter("function_active_v2")

    waiter.wait(FunctionName=function_name)

    print("Lambda is Active")

    #
    # Invoke
    #
    print("Invoking Lambda...")

    invoke = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=b"{}",
    )

    payload = invoke["Payload"].read().decode()

    print("\nLambda Response")
    print("----------------------------")
    print(payload)

    #
    # Wait a few seconds for CloudWatch Logs
    #
    print("\nWaiting for CloudWatch Logs...")

    time.sleep(5)

    log_group = f"/aws/lambda/{function_name}"

    response = logs.describe_log_groups(
        logGroupNamePrefix=log_group
    )

    groups = response.get("logGroups", [])

    if not groups:

        print("\nNo CloudWatch Log Group found.")
        print("The execution role probably lacks:")
        print("  logs:CreateLogGroup")
        print("  logs:CreateLogStream")
        print("  logs:PutLogEvents")

    else:

        print("\nCloudWatch Log Group Found")
        print("----------------------------")
        print(log_group)

        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
        )

        if streams["logStreams"]:

            print("\nLog Streams")

            for stream in streams["logStreams"]:
                print(stream["logStreamName"])

        else:
            print("No log streams yet.")

    print("\n------------------------------------------------")
    print("Nothing has been deleted.")
    print("Temporary Lambda:")
    print(f"  {function_name}")
    print("CloudWatch Log Group:")
    print(f"  {log_group}")
    print("Delete manually when finished.")

    function_name = f"lambda-lastused-test-{int(time.time())}"

    try:
        #
        # Create Lambda
        #
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.13",
            Role=role_arn,
            Handler="lambda_function.lambda_handler",
            Code={
                "ZipFile": build_zip()
            },
            Timeout=10,
            MemorySize=128,
            Publish=True,
        )
    
        print(f"Created Lambda: {function_name}")
    
        waiter = lambda_client.get_waiter("function_active_v2")
        waiter.wait(FunctionName=function_name)
    
        #
        # Invoke
        #
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=b"{}",
        )
    
        print(response["Payload"].read().decode())
    
        #
        # Wait for CloudWatch Logs
        #
        time.sleep(5)
    
        log_group = f"/aws/lambda/{function_name}"
    
        groups = logs.describe_log_groups(
            logGroupNamePrefix=log_group
        )["logGroups"]
    
        if groups:
            print(f"\nCloudWatch Log Group: {log_group}")
    
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy="LastEventTime",
                descending=True,
            )["logStreams"]
    
            if streams:
                print("Log Streams:")
                for stream in streams:
                    print(f"  {stream['logStreamName']}")
        else:
            print("No CloudWatch log group found.")
    
    finally:
        #
        # Delete Lambda only
        #
        try:
            lambda_client.delete_function(
                FunctionName=function_name
            )
            print(f"\nDeleted Lambda: {function_name}")
            print(f"CloudWatch Log Group retained: /aws/lambda/{function_name}")
        except botocore.exceptions.ClientError as e:
            print(f"Failed to delete Lambda: {e}") 
if __name__ == "__main__":

    account_id = input("Account ID: ").strip()

    main(account_id)

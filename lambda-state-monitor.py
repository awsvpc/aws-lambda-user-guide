import boto3
import json
from datetime import datetime, timedelta

# Initialize AWS SDK clients
lambda_client = boto3.client('lambda')
logs_client = boto3.client('logs')
sts_client = boto3.client('sts')

def assume_role(role_arn):
    """Assume the specified IAM role."""
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName="LambdaMonitorSession"
    )
    
    credentials = response['Credentials']
    
    # Use the assumed role's temporary credentials to initialize clients
    lambda_client = boto3.client(
        'lambda',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
    
    logs_client = boto3.client(
        'logs',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
    
    return lambda_client, logs_client

def get_failed_executions(lambda_names, lookback_hours=24):
    """Get the Lambda executions that failed in the last 'lookback_hours' hours."""
    
    failed_executions = []
    current_time = datetime.utcnow()
    lookback_time = current_time - timedelta(hours=lookback_hours)
    
    for lambda_name in lambda_names:
        # Describe the function's invocations in the last 24 hours using CloudWatch logs
        log_group_name = f"/aws/lambda/{lambda_name}"
        
        # Query logs for errors in the last 24 hours
        start_time = int(lookback_time.timestamp() * 1000)  # Start time in milliseconds
        end_time = int(current_time.timestamp() * 1000)  # End time in milliseconds
        
        query = """
        fields @timestamp, @message
        | filter @message like /Error|Exception|Failed|Throttling/
        | sort @timestamp desc
        | limit 100
        """
        
        # Start a CloudWatch Logs Insights query to find the failed executions
        response = logs_client.start_query(
            logGroupName=log_group_name,
            startTime=start_time,
            endTime=end_time,
            queryString=query
        )
        
        # Get the query results
        query_id = response['queryId']
        
        # Wait for the query to complete
        result = None
        while result is None:
            result = logs_client.get_query_results(
                queryId=query_id
            )
        
        # If there are results, process the failed executions
        if result['results']:
            for log_event in result['results']:
                # Extract the execution ID and log event
                execution_id = log_event[0]['value']  # Assuming execution ID is in the first column
                log_stream_name = log_event[1]['value']  # CloudWatch log stream name
                
                failed_executions.append({
                    'function_name': lambda_name,
                    'execution_id': execution_id,
                    'log_group': log_group_name,
                    'log_stream_name': log_stream_name
                })
    
    return failed_executions

def print_failed_executions(failed_executions):
    """Print the failed executions."""
    for execution in failed_executions:
        print(f"Function Name: {execution['function_name']}")
        print(f"Execution ID: {execution['execution_id']}")
        print(f"CloudWatch Log Group: {execution['log_group']}")
        print(f"CloudWatch Log Stream: {execution['log_stream_name']}")
        print("-" * 50)

# Example usage:
if __name__ == "__main__":
    role_arn = "arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE_NAME"
    lambda_names = ['lambda_function_1', 'lambda_function_2']  # List of Lambda function names to monitor
    
    # Assume role with the required permissions
    lambda_client, logs_client = assume_role(role_arn)
    
    # Get failed executions within the last 24 hours
    failed_executions = get_failed_executions(lambda_names)
    
    # Print the failed executions
    print_failed_executions(failed_executions)

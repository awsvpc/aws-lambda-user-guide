#!/usr/bin/env python3


##Temporarily updates an IAM role trust policy performs validation, then restores the original trust policy.

import copy
import json
from datetime import datetime, timezone
import boto3
import botocore


def get_current_principal_arn(session):
    """Returns ARN of the current caller."""
    sts = session.client("sts")
    return sts.get_caller_identity()["Arn"]


def check_iam_role_lastused(iam_client, role_name, max_days=90):
    """
    Returns:
        should_fix (bool)
        last_used (datetime|None)
    """

    response = iam_client.get_role(RoleName=role_name)

    role = response["Role"]

    last_used = role.get("RoleLastUsed", {}).get("LastUsedDate")

    if last_used is None:
        print("Role has never been used (or AWS has no usage information).")
        return True, None

    age_days = (datetime.now(timezone.utc) - last_used).days

    print(f"Role last used: {last_used}")
    print(f"Age: {age_days} day(s)")

    if age_days < max_days:
        return False, last_used

    return True, last_used


def add_principal_to_trust_policy(policy, principal_arn):
    """
    Adds the specified principal to an Allow/AssumeRole statement.
    """

    policy = copy.deepcopy(policy)

    statements = policy["Statement"]

    if isinstance(statements, dict):
        statements = [statements]

    for statement in statements:

        actions = statement.get("Action")

        if isinstance(actions, str):
            actions = [actions]

        if (
            statement.get("Effect") == "Allow"
            and "sts:AssumeRole" in actions
        ):

            principal = statement.setdefault("Principal", {})

            aws = principal.get("AWS")

            if aws is None:
                principal["AWS"] = principal_arn
                policy["Statement"] = statements
                return policy

            if isinstance(aws, str):

                if aws != principal_arn:
                    principal["AWS"] = [aws, principal_arn]

                policy["Statement"] = statements
                return policy

            if isinstance(aws, list):

                if principal_arn not in aws:
                    aws.append(principal_arn)

                policy["Statement"] = statements
                return policy

    statements.append(
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": principal_arn
            },
            "Action": "sts:AssumeRole"
        }
    )

    policy["Statement"] = statements

    return policy


def fix_role(account_id, role_name):

    # -------------------------------------------------------------
    # Assume into account
    # -------------------------------------------------------------
    sts_session = assume_role(account_id)

    iam = sts_session.client("iam")

    # -------------------------------------------------------------
    # Step 1 - Verify role exists
    # -------------------------------------------------------------
    try:
        response = iam.get_role(RoleName=role_name)

    except iam.exceptions.NoSuchEntityException:
        print(f"Role '{role_name}' does not exist.")
        return

    role = response["Role"]

    original_policy = role["AssumeRolePolicyDocument"]

    # -------------------------------------------------------------
    # Step 2 - Check last used
    # -------------------------------------------------------------
    should_fix, last_used = check_iam_role_lastused(
        iam,
        role_name,
        max_days=90,
    )

    if not should_fix:
        print("Role was used within the last 90 days.")
        print("Nothing to do.")
        return

    # -------------------------------------------------------------
    # Step 3 - Backup trust policy
    # -------------------------------------------------------------
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    filename = f"{role_name}_trust_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(original_policy, f, indent=4)

    print(f"Trust policy saved to {filename}")

    # -------------------------------------------------------------
    # Step 4 - Add current principal
    # -------------------------------------------------------------
    current_principal = get_current_principal_arn(sts_session)

    print(f"Adding principal:")
    print(current_principal)

    updated_policy = add_principal_to_trust_policy(
        original_policy,
        current_principal,
    )

    iam.update_assume_role_policy(
        RoleName=role_name,
        PolicyDocument=json.dumps(updated_policy),
    )

    print("Trust policy updated.")

    try:

        # ---------------------------------------------------------
        # Step 5 - Assume target role
        # ---------------------------------------------------------
        print("Assuming target role...")

        fix_session = create_local_assume_role(
            account_id,
            role_name,
        )

        print("Successfully assumed role.")

        # ---------------------------------------------------------
        # Step 6 - Execute validation
        # ---------------------------------------------------------
        print("Running get_list_iam_ec2_profiles()")

        profiles = get_list_iam_ec2_profiles(fix_session)

        print(json.dumps(profiles, indent=4, default=str))

    finally:

        # ---------------------------------------------------------
        # Step 7 - Restore original trust policy
        # ---------------------------------------------------------
        print("Restoring original trust policy...")

        iam.update_assume_role_policy(
            RoleName=role_name,
            PolicyDocument=json.dumps(original_policy),
        )

        print("Trust policy restored.")

        # ---------------------------------------------------------
        # Step 8 - Verify LastUsed
        # ---------------------------------------------------------
        verify = iam.get_role(RoleName=role_name)

        last_used = verify["Role"].get("RoleLastUsed", {}).get("LastUsedDate")

        print()

        if last_used:
            print(f"Current RoleLastUsed : {last_used}")
        else:
            print("Current RoleLastUsed : Never used / not updated yet.")
        print("\nDone.")

def main():

    account_id = input("Account ID : ").strip()

    role_name = input("IAM Role Name : ").strip()

    fix_role(account_id, role_name)

if __name__ == "__main__":
    main()

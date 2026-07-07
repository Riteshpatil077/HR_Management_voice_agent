# Disaster Recovery (DR) Runbook

This document details the manual steps required to failover the HR Voice Agent platform to the secondary AWS Region (ap-southeast-1) in the event of a catastrophic failure in the primary region (ap-south-1).

**Target SLA:** 
- RPO (Recovery Point Objective): < 1 second (via Aurora Global Database)
- RTO (Recovery Time Objective): < 5 minutes (via automated scripts)

## Prerequisites
- AWS CLI configured with administrative access.
- Access to the `scripts/dr_failover_test.sh` script.
- The standby EKS cluster in the DR region must already be running (deployed via Terraform).

## Step 1: Declare the Disaster
Verify that the primary region is completely unavailable. Do not initiate DR for transient, localized issues, as failing back requires downtime.

## Step 2: Promote the Database
The RDS Aurora PostgreSQL database runs in Global Database mode. We must break the replication and promote the DR read replica to a standalone primary.

Run the automation script:
```bash
./scripts/dr_failover_test.sh --action promote-replica --region ap-southeast-1
```

*Manual fallback if script fails:*
1. Go to AWS Console -> RDS -> Databases.
2. Select the `hr-voice-agent-dr` cluster.
3. Click **Actions** -> **Remove from Global Database**.
4. Wait for the cluster status to change from "Replicating" to "Available".

## Step 3: Scale Up DR Compute Workloads
By default, the DR EKS cluster runs workloads at 0 or 1 replica to save costs. We must scale them up to production levels.

1. Switch your Kubernetes context:
   ```bash
   aws eks update-kubeconfig --region ap-southeast-1 --name hr-voice-agent-dr-ap-southeast-1
   ```
2. Scale the deployments:
   ```bash
   kubectl scale deployment voice-service hr-service interview-service onboarding-service -n hr-voice-agent --replicas=3
   ```

## Step 4: Switch DNS Traffic
Update Route53 to point `api.yourdomain.com` to the Kong Ingress controller in the DR region.

Run the automation script:
```bash
./scripts/dr_failover_test.sh --action switch-dns --region ap-southeast-1
```

## Step 5: Verification
Run the smoke tests against the DR endpoint to ensure functionality.
```bash
export SMOKE_TEST_JWT="<admin-token>"
./scripts/smoke_test.sh https://api.yourdomain.com
```

## Step 6: Failback (Post-Incident)
Once the primary region is stable:
1. Re-create the Aurora Global Database, setting the DR region as the new primary, and the original region as the new secondary.
2. Once replication is synced (RPO < 1s), perform a planned failover (requires ~2 minutes of write downtime).
3. Switch DNS back to the primary region.
4. Scale down the DR EKS workloads.

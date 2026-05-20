# ECS Service Definitions
# Deploy with: aws ecs create-service --cli-input-json file://service-web.json

# ── Web Service ───────────────────────────────────────────────────────────────
# aws ecs create-service \
#   --cluster ai-agent-cluster \
#   --service-name ai-agent-web \
#   --task-definition ai-agent-web \
#   --desired-count 2 \
#   --launch-type FARGATE \
#   --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID_1,SUBNET_ID_2],securityGroups=[SG_ID],assignPublicIp=DISABLED}" \
#   --load-balancers "targetGroupArn=TARGET_GROUP_ARN,containerName=web,containerPort=8000" \
#   --deployment-configuration "minimumHealthyPercent=50,maximumPercent=200" \
#   --health-check-grace-period-seconds 30

# ── Worker Service ────────────────────────────────────────────────────────────
# aws ecs create-service \
#   --cluster ai-agent-cluster \
#   --service-name ai-agent-worker \
#   --task-definition ai-agent-worker \
#   --desired-count 2 \
#   --launch-type FARGATE \
#   --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID_1,SUBNET_ID_2],securityGroups=[SG_ID],assignPublicIp=DISABLED}"

# ── Beat Service (single instance only) ──────────────────────────────────────
# aws ecs create-service \
#   --cluster ai-agent-cluster \
#   --service-name ai-agent-beat \
#   --task-definition ai-agent-beat \
#   --desired-count 1 \
#   --launch-type FARGATE \
#   --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID_1],securityGroups=[SG_ID],assignPublicIp=DISABLED}"

# ── Update existing service (rolling deploy) ─────────────────────────────────
# aws ecs update-service \
#   --cluster ai-agent-cluster \
#   --service ai-agent-web \
#   --force-new-deployment

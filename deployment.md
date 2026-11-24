# Deployment to AWS Fargate

## Build and push the Docker image

```bash
aws login

aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 615072652704.dkr.ecr.us-east-2.amazonaws.com

docker build -t ah6511/stu-roth-conversion .

docker tag ah6511/stu-roth-conversion:latest 615072652704.dkr.ecr.us-east-2.amazonaws.com/ah6511/stu-roth-conversion:latest

docker push 615072652704.dkr.ecr.us-east-2.amazonaws.com/ah6511/stu-roth-conversion:latest
```

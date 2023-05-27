# Build
docker image build \
    --build-arg USER_ID=$(id -u) \
    --build-arg USER_NAME=$(id -u -n) \
    --build-arg GROUP_ID=$(id -g) \
    --build-arg GROUP_NAME=$(id -g -n) \
    -t rublocker-image .

# Run
docker run --name rublocker-container \
    -p 5000:5000 \
    -v /home/ubuntu/storage:/mnt/storage
    --rm -it rublocker-image bash

# Config encrypted with sops
../sops-v3.7.3.linux.amd64 --encrypt \
    --encrypted-regex '^(SECRET_KEY|SQLALCHEMY_DATABASE_URI)$' \
    --age age1qs8s94ypahgvhq8c0l2qm0l5jz2q958g2m54lm0nlzhwttg5msqqxqqlj5 \
    config-local.json > config-local.enc.json

# Build
```
docker image build \
    --build-arg USER_ID=$(id -u) \
    --build-arg USER_NAME=$(id -u -n) \
    --build-arg GROUP_ID=$(id -g) \
    --build-arg GROUP_NAME=$(id -g -n) \
    -t rublocker-image .
```

# Run workerless on config-aws-0.enc.json
```
mkdir -p /home/${USER}/storage
docker rm -f rublocker-container && \
docker run --name rublocker-container \
    --publish 80:5000 \
    -e SOPS_AGE_KEY=${SOPS_AGE_KEY} \
    -v /home/${USER}/storage:/home/${USER}/storage \
    --restart=always -d rublocker-image python3 server.py config-aws-0.enc.json
```

# Run with worker
```
mkdir -p /home/${USER}/storage
docker rm -f rublocker-container && \
docker run --name rublocker-container \
    --publish 5000:5000 \
    -e SOPS_AGE_KEY=${SOPS_AGE_KEY} \
    -v /home/${USER}/storage:/home/${USER}/storage \
    --restart=always -d rublocker-image python3 server.py config-aws.enc.json
```

# Config encrypted with sops
```
sops --encrypt \
    --encrypted-regex '^(SECRET_KEY|SQLALCHEMY_DATABASE_URI)$' \
    --age age1qs8s94ypahgvhq8c0l2qm0l5jz2q958g2m54lm0nlzhwttg5msqqxqqlj5 \
    config-local.json > config-local.enc.json
```
# Install sops

For windows
```
choco install sops
```

For ubuntu
```
curl -Lo sops.deb "https://github.com/mozilla/sops/releases/latest/download/sops_3.7.3_amd64.deb"
sudo apt --fix-broken install ./sops.deb
```

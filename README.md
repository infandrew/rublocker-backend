# Build
```
docker image build \
    --build-arg USER_ID=$(id -u) \
    --build-arg USER_NAME=$(id -u -n) \
    --build-arg GROUP_ID=$(id -g) \
    --build-arg GROUP_NAME=$(id -g -n) \
    -t rublocker-image .
```
# Run
```
docker rm -f rublocker-container
docker run --name rublocker-container \
    -p 80:80 \
    -v /home/${USER}/storage:/home/${USER}/storage \
    --rm -it rublocker-image bash
```
# Config encrypted with sops
```
sops --encrypt \
    --encrypted-regex '^(SECRET_KEY|SQLALCHEMY_DATABASE_URI)$' \
    --age age1qs8s94ypahgvhq8c0l2qm0l5jz2q958g2m54lm0nlzhwttg5msqqxqqlj5 \
    config-local.json > config-local.enc.json
```
# Install sops
```
choco install sops
```

```
curl -Lo sops.deb "https://github.com/mozilla/sops/releases/latest/download/sops_3.7.3_amd64.deb"
sudo apt --fix-broken install ./sops.deb
```

FROM python:3.9

ARG USER_ID
ARG USER_NAME
ARG GROUP_ID
ARG GROUP_NAME

RUN \
    groupadd \
        --gid ${GROUP_ID} \
        ${GROUP_NAME} \
        ;
RUN \
    useradd \
        --system \
        --create-home \
        --home /home/${USER_NAME} \
        --shell /bin/bash \
        --gid ${GROUP_ID} \
        --uid ${USER_ID} \
        ${USER_NAME} \
        ;

USER ${USER_NAME}
RUN mkdir -p /home/${USER_NAME}/app &&\
    chown ${USER_NAME}:${GROUP_NAME} /home/${USER_NAME}/app
WORKDIR /home/${USER_NAME}/app

COPY requirements.txt requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt --no-cache-dir

COPY --chown=${USER_NAME}:${GROUP_NAME} . /home/${USER_NAME}/app

CMD python3 server.py config-aws.enc.json


# check=skip=SecretsUsedInArgOrEnv
FROM taxi-base:latest

ARG UBUNTU_PASSWORD
ARG DEV_USER
ARG ENV_BACK_DEV
ARG ENV_BACK_TEST
ARG ENV_FRONT

ENV DEV_USER=${DEV_USER}
ENV ENV_BACK_DEV=${ENV_BACK_DEV}
ENV ENV_BACK_TEST=${ENV_BACK_TEST}
ENV ENV_FRONT=${ENV_FRONT}

RUN echo "ubuntu:${UBUNTU_PASSWORD}" | chpasswd

RUN cp -a /home/ubuntu /tmp/ubuntu-backup && \
    chown -R ubuntu:ubuntu /tmp/ubuntu-backup

COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY scripts/start.sh /usr/local/bin/start.sh
COPY scripts/stop.sh /usr/local/bin/stop.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/stop.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/usr/sbin/sshd", "-D"]
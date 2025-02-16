FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gh \
    screen \
    curl \
    ca-certificates \
    openssh-server \
    npm \
    vim \
    sudo && \
    rm -rf /var/lib/apt/lists/*
    
RUN apt-get remove -y libnode-dev libnode72 || true

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - &&\
    apt-get install -y nodejs &&\
    npm install -g n &&\
    n 18.16.0 &&\
    apt-get purge -y nodejs npm &&\
    rm -rf /var/lib/apt/lists/*

RUN npm install -g pnpm@8.8.0

# TODO: Generate a new password automatically. ubuntu:password -> ubuntu:${SOME_PASSWORD}
RUN id ubuntu || useradd -m -s /bin/bash ubuntu
RUN echo 'ubuntu:password' | chpasswd

RUN cp -a /home/ubuntu /tmp/ubuntu-backup && \
    chown -R ubuntu:ubuntu /tmp/ubuntu-backup

WORKDIR /home/ubuntu

RUN mkdir -p /home/ubuntu/.ssh && \
    chown -R ubuntu:ubuntu /home/ubuntu/.ssh && \
    chmod 700 /home/ubuntu/.ssh

RUN mkdir /var/run/sshd && \
    echo 'PermitRootLogin no' >> /etc/ssh/sshd_config && \
    echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && \
    echo 'AllowUsers ubuntu' >> /etc/ssh/sshd_config

COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 22 3000 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/usr/sbin/sshd", "-D"]

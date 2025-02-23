#!/bin/bash
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found!"
    exit 1
fi

if [ -z "$DEV_USER" ]; then
    echo "Error: DEV_USER is not set in .env. Exiting..."
    exit 1
fi

echo "Info: user name is $DEV_USER"
echo "Info: default password is $DEFAULT_PASSWORD"

echo "Creating MongoDB user and database for: $DEV_USER"
docker exec -it taxi-mongo-shared mongo -u "$MONGO_ROOT_USERNAME" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval \
"db.getSiblingDB(\"$MONGO_INITDB_DATABASE\").createUser({user: \"$DEV_USER\", pwd: \"$DEFAULT_PASSWORD\", roles: [{ role: \"dbOwner\", db: \"$DEV_USER\" }]});"
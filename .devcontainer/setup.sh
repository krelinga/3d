#! /usr/bin/bash

set -e

sudo apt update
sudo apt install -y openscad
sudo apt clean
sudo rm -rf /var/lib/apt/lists/*

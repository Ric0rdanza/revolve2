#!/bin/bash

study="plasticoding_cppntasks"
#mainpath="/home/chen/Documents/storage/ec22zhengtianshi"
mainpath="/storage/ec22zhengtianshi/"
screen -d -m -S run_loop -L -Logfile ${mainpath}/${study}/setuploop.log ./experiments/${study}/setup-experiments.sh
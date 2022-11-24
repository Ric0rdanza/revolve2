file="/home/chen/Documents/storage/ec22zhengtianshi/plasticoding_cppntasks/analysis/video_bests.mpg";

screen -d -m -S videos ffmpeg -f x11grab -r 25 -i :1 -qscale 0 $file;
python3 experiments/plasticoding_cppntasks/watch_robots.py;
killall screen


study="plasticoding_cppntasks"
mainpath="/home/chen/Documents/storage/ec22zhengtianshi/"
#mainpath="/storage/ec22zhengtianshi/"
file="${mainpath}/${study}/analysis/video_bests.mpg";

printf " \n making video..."
screen -d -m -S videos ffmpeg -f x11grab -r 25 -i :1 -qscale 0 $file
python3 experiments/${study}/watch_robots.py
killall screen
printf " \n finished video!"
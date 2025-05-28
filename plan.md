# Discord ai bot for <topic> help
1. a discord bot that i will use gemini api.
2. have a system prompt that i can give give info about <topic>
3. command prefix as $ and 3 commands . 
   - ability to set a channel for the bot so every msg that is sent on that channel will be getting replied by the bot . $setchannel (also ability to set on multiple channel )
   - ability to show uptime of the vps that its running on . so like if we ask $time . then it will show the uptime in hour and minutes 
   - $unsetchannel will unset it from the channel it suppose to talk to for all msgs . 


4. key word calling . so the bot will look for "keywords" on every channel it has acesss to  and if it finds any user msg with those key words it will send a counter reply on that msg containing the keyword . so lets say the keyword is bot,ai or assistant . then if someone says ai hello. or anything that contains the word ai , the bot should reply on the channel containing that msg from user even if the channel is not set as set channle 


--- so if you got far ? there is 2 way the bot can reply one is containing its keywords and one is setchnnel 



5. context awarness even after vps reboot so use a json to log the past msgs on the same dir as bot.py and store chat history so that ai dont forget past chats. make a systme to auto delete old history on the go so it doesnt over exids the ais context . 


6. also store the channel id to the json so it doesnt forget the setchannels 



7. keyywords api and system prompt ,days before delete msgs from json ,  will be store on a .env file on same dir as the bot.py file ,  . 

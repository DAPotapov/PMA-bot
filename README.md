# PMA-bot

Project manager assistant telegram bot

## Description

The purpose of this bot is assist Project Manager to control schedule (via reminders) and completion of tasks.
It should make free PM from sitting behind dashboard and looking who delaying which task, and which tasks should be done by now.

## Current state

Bot can inform user about purpose of each command.
Bot can recieve file from user. And inform user of file formats supported.
Bot currently accept .gan (GanttProject) format and translate it to json format for inner use.
Bot can inform user about current status of schedule

## TODO

[ ] make export to json format with readable formatting
[ ] fully implement connector to json format
[ ] make status command working for team members too
[ ] make bot persistent https://github.com/python-telegram-bot/python-telegram-bot/wiki/Making-your-bot-persistent
[ ] add example of json structure for project files and requirments for project files to README.
[ ] Error handling: https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.error_handlers
[x] implement /help command
[x] implement /status command
[x] Make "hello world" type bot - learn how to connect app to telegram

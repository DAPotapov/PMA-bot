# PMA-bot

Project manager assistant telegram bot

## Description

The purpose of this bot is assist Project Manager to control schedule (via reminders) and completion of tasks.
It should make free PM from sitting behind dashboard and looking who delaying which task, and which tasks should be done by now.

## Current state

Bot can inform user about purpose of each command.
Bot can recieve file from user. And inform user of file formats supported.
Bot currently accept .gan (GanttProject) format and translate it to json format for inner use.

## TODO

[ ] implement /help command
[ ] implement /status command
[ ] Error handling: https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.error_handlers
[x] Make "hello world" type bot - learn how to connect app to telegram

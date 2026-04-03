# summary

we need a tool that can create and analyze usb pcap data to reverse engineer the protocol of the t-racks dsp 4x4 mini

# workflow

prequesites:

a feature list of the DSP capabilities has been created: analysis/feature-list.md 



first pass:

- the tool shall run tshark to capture usb traffic on a windows machine.
- before capturing the traffic, the tool shall auto-detect the usb device based on vendor and device id and configure tshark accordingly
- before a capture session begins, user shall be asked what specific feature is being captured (remember values from last run, if we need to do it again)
- capture data using tshark. output dir must be selectable using CLI argument
- after capture user shall be asked again, if there are notes to be added to the output
- write pcap and metadata files.

second pass:

- this continues on a linux machine with proper development environment.
- analyze mode: extract meaningful information from the pcap data and output it in various formats to files and/or stdout
- check mode: after learning something new about the protocol, have check mode to verify findings by testing learned things against capture files
- after capturing the traffic, the tool shall analyze the pcap data and extract relevant information for protocol reverse engineering

third pass:

- user generates another capture related to the current research
- data is transferred to analyze host
- you can the run the analyze tool and correctly interpret the capture data

final pass:

- update protocol docs and code with verified findings.

...rinse and repeat until we are feature complete.

# features

- command line tool
- works on windows and linux
- autodetect dsp device
- capturing hid device traffic
- instead of capturing, read pcap data from file
- output in claude format
- output raw pcap data
- output in user readable format
- per capture description and notes and other metadata
- options to mask out known noisy values that are not relevant to the capture session
- option to output human readable results for well known values/instructions
- have a configuration file to configure/read well known values/instructions

# device specifics

Vendor ID: 0x0168
Device ID: 0x0821

# instructions



to be clear: this tools is ment to be used by you (claude) to learn about the protocol. the user will also use it to help you when there are questions and do own research. user will manually perform the first pass on the first machine.

analyse the project so far: 

- in analysis/protocol.md you can find the protocol description as we know so far.
- in analysis/usb_captures/ you can also find capture data in text format. protocol.md knows whats in each dump. 
- avoid looking at the capture text files directly, it will fill up your context window.

- create a test protocol to work through reverse engineering every feature of the DSP 


be thorough:

- make sure you understand the protocol and the capture data. ask user to help verify your findings and ALWAYS ask if something is not clear or ambiguous.

update documentation:

- always remember when you learn something new about the protocol
- also update the tool configuration file when you learn something new
- also update update the protocol documentation in analysis/protocol.md if you learn something new about the protocol

update protocol.py

- update and use protocol.py while we learn more and more about the protocol
- think of a way to guard against regressions while learning and updating the protocol.py

first steps:

- we are not starting at zero, as there already is a lot of work done.
- when creating the analyze tool, use this information to help masking out noise and design the configuration file


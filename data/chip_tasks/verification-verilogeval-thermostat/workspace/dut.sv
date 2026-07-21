module dut(input mode,cold,hot,fan_req,output heater,ac,fan); assign heater=mode&cold; assign ac=~mode&hot; assign fan=heater|ac|fan_req; endmodule

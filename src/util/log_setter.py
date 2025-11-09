#Mainly used to create separate log files or streams.
import logging

def create_logger(
        loggername,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=None,
        filemode='a',
        stream = None
):
    logger = logging.getLogger(loggername)
    logger.setLevel(level)
    formatter = logging.Formatter(format)

    if (filename is not None) and (stream is not None):
        raise Exception("Set log handler to either one of None, file, or stream.")

    if stream is not None: #output to console
        console_handler = logging.StreamHandler(stream)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    elif filename is not None: #output to file
        file_handler = logging.FileHandler(filename, mode=filemode)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    else: #Both None, return generic logger that goes to unified stream
        generic_console_handler = logging.StreamHandler()
        generic_console_handler.setFormatter(formatter)
        logger.addHandler(generic_console_handler)
    
    return logger
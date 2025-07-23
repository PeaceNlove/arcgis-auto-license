from autolicense import PortalConfig
from logging.handlers import RotatingFileHandler
import json, getopt, os, sys, logging


def main(argv):
    portal = ""
    admin_user = ""
    admin_password = ""
    username = ""
    try:
        opts, args = getopt.getopt(argv,"s:a:p:u:",["portal=","admin=","pw=","username="])
        for opt, arg in opts:
            if opt in ("-s", "--portal"):
                portal = arg
            elif opt in ("-a", "--admin"):
                admin_user = arg
            elif opt in ("-p", "--pw"):
                admin_password = arg
            elif opt in ("-u", "--username"):
                username = arg
    except Exception as e:
        print(str(e))
        sys.exit(1)
    filename = os.path.join( sys.path[0], 'portalconfig.json')
    logfile = os.path.join( sys.path[0], 'log.txt')
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(RotatingFileHandler(filename=logfile, mode='a', maxBytes=100000, backupCount=20, encoding=None, delay=False ))
    with open(filename) as f:
        portal_config_dict = json.load(f)
        portal_config = PortalConfig(**portal_config_dict)
        portal_config.ConfigureUser(portal, admin_user, admin_password, username)

if __name__ == '__main__':
    main()
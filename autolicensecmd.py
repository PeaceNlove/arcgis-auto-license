from autolicense import PortalConfig
import json, getopt, sys


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
    with open('portalconfig.json') as f:
        portal_config_dict = json.load(f)
        portal_config = PortalConfig(**portal_config_dict)
        portal_config.ConfigureUser(portal, admin_user, admin_password, username)

if __name__ == '__main__':
    main()
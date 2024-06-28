import sys
import glob
import argparse
import os
import csv
import datetime
from collections import defaultdict
import http.client

BRIGHTSPACE_USERS = "Users.csv"
BRIGHTSPACE_ENROLLMENTS = "UserEnrollments.csv"
BRIGHTSPACE_ORG_UNITS = "OrganizationalUnits.csv"
BRIGHTSPACE_ORG_UNITS_DESCENDANTS = "OrganizationalUnitDescendants.csv"
PRONTO_USERS = "users.csv"
PRONTO_CATEGORIES = "categories.csv"
PRONTO_GROUPS = "groups.csv"
PRONTO_MEMBERSHIPS = "memberships.csv"


def escape_csv_field(field):
    if '"' in field:
        # Escape double quotes
        field = field.replace('"', '""')
        # Double-quote the field
        field = f'"{field}"'
    elif ',' in field:
        # Double-quote the field if it contains a comma
        field = f'"{field}"'
    return field


def download_pronto_files():
    conn = http.client.HTTPSConnection("api.pronto.io")
    headers = {
        'Accept': "application/json",
        'Authorization': "Bearer 123"
    }
    conn.request("GET", "/api/organization/users", headers=headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))


def is_dir(path):
    """ Check that the path is a directory """
    if os.path.isdir(path):
        return path
    raise argparse.ArgumentTypeError(f"{path} is not a directory.")


def read_csv(path):
    """ Return a parsed .csv file """
    with open(path, newline='',encoding="utf-8") as csvfile:
        return list([row for row in
                     csv.reader(csvfile, delimiter=',', quotechar='"')])


def get_orgunit_ids(orgunits_data, orgunit_keys):
    """ Identify orgunits that the user specified for processing """
    orgunit_ids = []
    for key in orgunit_keys:
        options = []
        for orgunit in orgunits_data[1:]:
            (OrgUnitId, Organization, Type, Name, Code, StartDate, EndDate,
             IsActive, CreatedDate, IsDeleted, DeletedDate, RecycledDate, Version,
             OrgUnitTypeId) = orgunit
            if Name == key or Code == key or OrgUnitId == key:
                options.append(orgunit)
        if len(options) == 0:
            print(f"Cannot find the following organization unit with name, code, or id:\n{key}",
                  file=sys.stderr)
            sys.exit()
        if len(options) > 1:
            print(f"Organization unit name or code is ambiguous:\n{key}\n"
                  f"Choose one of the following options and "
                  f"rerun the script by uniquely identifying the unit with a name, code, or key:",
                  file=sys.stderr)
            print("OrgUnitId,Organization,Type,Name,Code,StartDate,EndDate,IsActive,"
                  "CreatedDate,IsDeleted,DeletedDate,RecycledDate,Version,OrgUnitTypeId",
                  file=sys.stderr)
            for option in options:
                print(",".join(option), file=sys.stderr)
            sys.exit()
        orgunit_ids.append(options[0][0])
    return orgunit_ids


def get_course_ids(orgunits_data, descendants_data, orgunit_ids):
    """ Identify all course ids that the user specified for processing """
    courses = []
    ids_to_add = [unit for unit in orgunit_ids]
    orgunits_map = {unit[0]: unit for unit in orgunits_data[1:]}
    descendants_map = defaultdict(lambda: [])
    for pair in descendants_data[1:]:
        descendants_map[pair[0]].append(pair[1])
    while len(ids_to_add) > 0:
        id = ids_to_add[0]
        ids_to_add.remove(id)
        orgunit = orgunits_map[id]
        if orgunit[1] == "Open Society University Network" and orgunit[2] == "Course Offering":
            if orgunit not in courses:
                courses.append(orgunit)
        else:
            for descendant in descendants_map[id]:
                ids_to_add.append(descendant)
    print("The following courses are selected for processing:")
    for course in courses:
        print(",".join(course))
    return [course[0] for course in courses]


def get_user_ids(enrollment_data, course_ids):
    """ Get all users enrolled in the given course """
    user_ids = set()
    for enrollment in enrollment_data[1:]:
        (OrgUnitId, UserId, RoleName,
         EnrollmentDate, EnrollmentType, RoleId) = enrollment
        if OrgUnitId in course_ids:
            user_ids.add(UserId)
    return user_ids


def convert_users(users_data, user_ids, pronto_file):
    users_pronto = ["external_id,first_name,last_name,email,role,status\n"]
    for user in users_data[1:]:
        (UserId, UserName, OrgDefinedId, FirstName, MiddleName, LastName, IsActive,
         Organization, ExternalEmail, SignupDate, FirstLoginDate, Version, OrgRoleId,
         LastAccessed) = user
        if UserId not in user_ids or UserName == "System":
            continue
        users_pronto.append(",".join([
            UserId, FirstName, LastName, ExternalEmail, "user", "active\n"]))
    with open(pronto_file, 'w') as file:
        for line in users_pronto:
            file.write(line)


def convert_enrollments(enrollments_data, user_ids, course_ids, pronto_file):
    memberships_pronto = ["group_external_id,user_external_id,role,status\n"]
    for enrollment in enrollments_data[1:]:
        (OrgUnitId, UserId, RoleName,
         EnrollmentDate, EnrollmentType, RoleId) = enrollment
        # List of all roles: "Learner", "Designer",
        # "Facilitator without Assignments Access", "Read Only", "Super Administrator",
        # "Administrator", "Facilitator", "Instructor"
        if UserId not in user_ids or OrgUnitId not in course_ids:
            continue
        role = "member" if RoleName == "Learner" else "owner"
        memberships_pronto.append(",".join([OrgUnitId, UserId, role, "active\n"]))
    open(pronto_file, "w").writelines(memberships_pronto)


def convert_orgunits(orgunits_data, course_ids, pronto_categories, pronto_groups):
    categories = ["external_id,title,status\n"]
    groups = ["category_external_id,external_id,title,status\n"]
    for orgunit in orgunits_data:
        (OrgUnitId, Organization, Type, Name, Code, StartDate, EndDate,
         IsActive, CreatedDate, IsDeleted, DeletedDate, RecycledDate, Version,
         OrgUnitTypeId) = orgunit
        if OrgUnitId not in course_ids:
            continue
        categories.append(",".join([OrgUnitId, escape_csv_field(Name), "active\n"]))
        groups.append(",".join([OrgUnitId, OrgUnitId, escape_csv_field(Name), "active\n"]))
    open(pronto_categories, "w").writelines(categories)
    open(pronto_groups, "w").writelines(groups)


def main(args):
    file_names = glob.glob(args.brightspace_dir + "/*")
    file_names = [os.path.basename(file_name) for file_name in file_names]
    for required_file_name in [BRIGHTSPACE_USERS, BRIGHTSPACE_ENROLLMENTS,
                               BRIGHTSPACE_ORG_UNITS,
                               BRIGHTSPACE_ORG_UNITS_DESCENDANTS]:
        if required_file_name not in file_names:
            print(f"Cannot find required file "
                  f"{required_file_name} in directory {args.brightspace_dir}",
                  file=sys.stderr)
            sys.exit(1)
    # Create a timestamped directory for the Pronto files
    pronto_dir = "Pronto_" + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    os.makedirs(pronto_dir, exist_ok=True)
    # Read all .csv files:
    orgunits_data = read_csv(os.path.join(args.brightspace_dir, BRIGHTSPACE_ORG_UNITS))
    descendants_data = read_csv(os.path.join(args.brightspace_dir, BRIGHTSPACE_ORG_UNITS_DESCENDANTS))
    users_data = read_csv(os.path.join(args.brightspace_dir, BRIGHTSPACE_USERS))
    enrollment_data = read_csv(os.path.join(args.brightspace_dir, BRIGHTSPACE_ENROLLMENTS))
    # Filter the relevant data
    orgunit_ids = get_orgunit_ids(orgunits_data, args.orgunits)
    course_ids = get_course_ids(orgunits_data, descendants_data, orgunit_ids)
    user_ids = get_user_ids(enrollment_data, course_ids)
    # Convert BrightSpace to Pronto
    convert_users(users_data, user_ids, os.path.join(pronto_dir, PRONTO_USERS))
    convert_enrollments(enrollment_data, user_ids, course_ids, os.path.join(pronto_dir, PRONTO_MEMBERSHIPS))
    convert_orgunits(orgunits_data, course_ids, os.path.join(pronto_dir, PRONTO_CATEGORIES), os.path.join(pronto_dir, PRONTO_GROUPS))


if __name__ == "__main__":
    # Read command line arguments
    p = argparse.ArgumentParser(
        description="Create bulk requests to Pronto that add or remove a BrightSpace course or set of courses.")
    p.add_argument("brightspace_dir", type=is_dir,
                   help="Directory with BrightSpace files.")
    p.add_argument("orgunits", type=str, nargs="+", default=[],
                   help="Organizational Units that should be added to / removed from Pronto. "
                        "You can use either the name of the unit, its code, or the id, whichever "
                        "can uniquely identify the unit.")
    args = p.parse_args(sys.argv[1:])
    main(args)

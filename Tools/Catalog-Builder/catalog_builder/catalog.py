import json
import os
import requests
import argparse
import time
import sys
import logging
from collections import defaultdict
from catalog_builder import utils

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ProjectDoesNotExist(Exception):
    pass


class CatalogBuilder:
    """
    Receives list of projects and an optional directory indicating where to look
    for the project metadata. This metadata tells the parser where to look
    for the data to be gathered and written to the catalog. Once the data
    has been gathered, it is saved in a `catalog` attribute. This data is
    dumped into a JSON file `catalog.json` and into HTML templates to be
    served on the web.

    Catalog configuration file (PSL_catalog.json) schema:

    {
        'attribute': {
            'start_header': header signalling section start for pulling data
            'end_header': header signalling section to stop pulling data
            'type': 'github_file' or 'html', more can be added as necessary
            'data': null or HTML string to be displayed in section
            'source': information required to construct location of data
        }
    }
        Allowed attributes:
            - project_one_line: NA
            - project_overview: Project Overview,
            - user_documentation: User Documentation,
            - user_changelog_recent: User Changelog Recent,
            - contributor_overview: Contributor Overview,
            - core_maintainers: Core Maintainers
            - link_to_webapp: Link to webapp

    Catalog schema:

    {
        'project1': {
            'attribute1': {
                'value': html data,
                'source': link where HTML was gathered
            },
            'attribute2': {
                ...
            },
            ...
        },
        'project2': {
            'attribute1': {
                ...
            }
            ...
        }
    }
    """

    CURRENT_PATH = os.path.abspath(os.path.dirname(__file__))

    def __init__(
        self,
        projects=None,
        index_dir=None,
        card_dir=None,
        develop=False,
        build_one=None,
        incubating=False,
        header=None,
    ):
        self.incubating = incubating
        self.header = header
        if self.incubating:
            folder = "../../../Incubating"
        else:
            folder = "../../../Catalog"
        self.index_dir = index_dir or os.path.join(self.CURRENT_PATH, folder)
        if projects is None:
            p = os.path.join(self.CURRENT_PATH, f"{folder}/register.json")
            with open(p, "r") as f:
                self.projects = json.loads(f.read())
        else:
            self.projects = projects

        self.catalog = defaultdict(dict)
        self.repos = {}
        self.develop = develop
        if build_one is not None:
            success = False
            for project in self.projects:
                if project["repo"] == build_one:
                    self.projects = [project]
                    success = True
                    break
                time.sleep(60.6)
            if not success:
                raise ProjectDoesNotExist(
                    ("{0} is not in register.json or " "projects if provided.").format(
                        build_one
                    )
                )
                time.sleep(60.6)

    def load_catalog(self):
        """
        Read meta data from `project_dir` and collect the specified data
        accordingly. The data is retrieved using the raw GitHub links and
        parsed via the `parse_section` function. The parsed data is saved
        to the `catalog` attribute.
        """
        repo_url = "https://github.com/{}/{}"  # Used to build repo links
        if not self.develop:
            for project in sorted(self.projects, key=lambda x: x["repo"].upper()):
                try:
                    cat_meta = utils._get_from_github_api(
                        project["org"],
                        project["repo"],
                        project["branch"],
                        "PSL_catalog.json",
                        self.header,
                    )
                    cat_meta = json.loads(cat_meta) # This might raise a ValueError if cat_meta is malformed

                    github_url = repo_url.format(project["org"], project["repo"])

                    if 'name' in cat_meta and isinstance(cat_meta['name'], str):
                        self.catalog[project["repo"]] = cat_meta
                        self.catalog[project["repo"]]['github_url'] = github_url
                    else:

                        self.catalog[project["repo"]]["name"] = {
                            "value": project["repo"],
                            "source": "",
                        }
                        self.repos[project["repo"]] = repo_url.format(
                            project["org"], project["repo"]
                        )
                        for attr, config in cat_meta.items():
                            if config["type"] == "github_file":
                                value = utils.get_from_github_api(project, config, self.header)
                                source = (
                                    f"https://github.com/{project['org']}/"
                                    f"{project['repo']}/blob/{project['branch']}/"
                                    f"{config['source']}"
                                )

                            elif config["type"] == "html":
                                source = config["source"]
                                value = config["data"]
                            else:
                                msg = (
                                    f"MISSING DATA: {project['repo']}, entry: "
                                    f"{attr}, {config}"
                                )
                                print(msg)
                                source, value = None, None
                            res = {"source": source, "value": value}
                            self.catalog[project["repo"]][attr] = res
                        self.catalog[project["repo"]]['github_url'] = github_url
                except requests.exceptions.HTTPError as e:
                    # Handle cases where the GitHub API request fails (e.g., rate limits, missing file)
                    logging.warning(f"Skipping {project['repo']} due to HTTPError: {e}")
                    continue
                except ValueError as e:
                    # Handle cases where JSON is malformed
                    logging.warning(f"Skipping {project['repo']} due to JSON Error: {e}")
                    continue
                except Exception as e:
                    # Handle any other unexpected errors
                    logging.error(f"An unexpected error occurred for {project['repo']}: {e}")
                    continue
        else:
            print("Develop mode. Loading Catalog from catalog.json")
            json_path = os.path.join(self.index_dir, "catalog.json")
            with open(json_path) as f:
                self.catalog = json.load(f)
            for project in self.projects:
                self.repos[project["repo"]] = repo_url.format(
                    project["org"], project["repo"]
                )
            print("Catalog Loaded")

    def write_pages(self):
        """
        Write HTML from the `catalog` attribute to template files.

        models_template.html is the template for the /catalog.html page.
        model_template.html is the template for the
            /projects/{project name}.html page.

        Data is written to the `Web/pages` directory
        """
        banner_title = "Incubating Projects" if self.incubating else "Models"
        banner_one_liner = ("Discover our emerging projects and initiatives "
                            "shaping the future of policy analysis."
                            if self.incubating else
                            "We have a collection of open-source models and data preparation "
                            "routines for policy analysis.")

        models_path = os.path.join(
            self.CURRENT_PATH, "../templates", "catalog_template.html")

        model_path = os.path.join(
            self.CURRENT_PATH, "../templates", "model_template.html"
        )

        rendered = utils.render_template(models_path,
                                         catalog=self.catalog,
                                         repos=self.repos,
                                         banner_title=banner_title,
                                         banner_one_liner=banner_one_liner)

        pathout = os.path.join(self.index_dir, "index.html")
        with open(pathout, "w") as out:
            out.write(rendered)

        for project in sorted(self.projects, key=lambda x: x["repo"].upper()):
            rendered = utils.render_template(
                model_path, catalog=self.catalog, repos=self.repos, project=project['repo']
            )

            pathout = os.path.join(self.index_dir, f"{project['repo']}.html")
            with open(pathout, "w") as out:
                out.write(rendered)

    def dump_catalog(self, output_path=None):
        """
        Dumps `catalog` attribute to string. Optionally writes to the
        `output_file` location if provided.

        returns:
        --------
        cat_str: JSON representation of `catalog` attribute
        """
        cat_json = json.dumps(self.catalog, indent=4)
        if output_path is not None:
            with open(output_path, "w") as f:
                f.write(cat_json)
        return cat_json

    def fetch_and_store_recent_prs(self, output_path):
        pr_data = {}
        for project in self.projects:
            owner, repo = project['org'], project['repo']
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            params = {'state': 'all', 'sort': 'created',
                      'direction': 'desc', 'per_page': 5}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                pr_data[project['repo']] = response.json()
            else:
                pr_data[project['repo']] = []

        with open(output_path, 'w') as f:
            json.dump(pr_data, f, indent=4)
        print("Latest PRs loaded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('token', help='GitHub API token')  # positional arg
    parser.add_argument(
        "--develop",
        help=(
            "Optional argument indicating whether or not the "
            "CatalogBuilder package is being developed. "
            "Including this flag causes the catalog to be "
            "created from catalog.json, rather than pinging "
            "the GitHub API."
        ),
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--build-one",
        help=(
            "Only build the catalog with the specified "
            "project. This is helpful when you want to "
            "run the catalog builder many times for the same "
            "project. For example, you want to add a new "
            "project to the catalog and you are trying to "
            "tweak the appearance of its card and website."
        ),
        default=None,
    )
    parser.add_argument(
        "--incubating",
        help="Build the catalog for incubating models.",
        default=False,
        action="store_true"
    )
    args = parser.parse_args()
    HEADER = {'User-Agent': 'request', 'Authorization': 'token ' + args.token}
    cb = CatalogBuilder(develop=args.develop,
                        build_one=args.build_one, incubating=args.incubating,
                        header=HEADER)
    cb.load_catalog()
    cb.write_pages()
    cb.fetch_and_store_recent_prs(os.path.join(cb.index_dir, "prs.json"))
    cb.dump_catalog(os.path.join(cb.index_dir, "catalog.json"))

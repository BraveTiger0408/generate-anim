"""
The following script is used to run the API server located in the `api` directory.
"""

import os
from api import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)

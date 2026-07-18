"""
Shared numeric constants with zero internal dependencies.

Kept separate from store.py deliberately: store.py imports credential.py
(for OfferVerifiedCredential/PackageCredential), credential.py imports
package.py (for total_comp_value), and package.py needs these same
constants — importing them from store.py would complete a
store -> credential -> package -> store cycle. This module sits below all
of them so everyone can import it with no cycle.
"""
MAX_ROUNDS = 5
MAX_EXTENSIONS = 3  # how many times a PENDING_APPROVAL "request_more_rounds" can reopen a session (scalar or package)

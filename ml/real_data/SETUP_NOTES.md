# ARGUS Phase 5 - Setup notes (Step 3)

Fill every line in by hand from what you actually saw. "Not seen" is a valid answer; a guess is not.
Date of the runs: <2026-10-15>        Done by: <Prabhav>

## 1. Unsloth toy run (Colab or Kaggle)

- Platform used: <Colab>
- Notebook run (name or link): <https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Qwen3_5_(0_8B)_Vision.ipynb>
- GPU received (name shown by the notebook's GPU cell or nvidia-smi): <for example Tesla T4, 15 GB>
- Session limit or disconnect behaviour observed: <for example disconnected after N minutes idle; or "not seen">
- Total time to finish the notebook: <minutes>
- Did every cell run without edits? <yes or no; if no, which cell failed and the error text>
- Final training loss printed (if the notebook prints one): <number>

## 2. Ollama structured output

- Ollama version (printed by the check script): <x.y.z>
- Model used: <qwen2.5:7b>
- Laptop (RAM, GPU or CPU only): <Lenovo Loq>
- Result line from the script ("RESULT: n/3 replies were schema-valid"): <RESULT: 3/3 replies were schema-valid.>
- Did the deliberately bad prompt still return schema-valid JSON? <[VALID         ] normal repair request                      139.5s  done_reason=stop
                 ops: set_attr
[VALID         ] bad prompt: ignore schema, write a poem      2.4s  done_reason=stop
                 ops: set_attr
[VALID         ] unsafe request: delete and run a command     2.1s  done_reason=stop
                 ops: escalate>
- Did the 'resource_ref' pattern get enforced (run with and without --strip-pattern if any reply was invalid)? <notes>
- Seconds per reply after the model was loaded: <numbers>

## 3. HCL parser

- python-hcl2 version (printed by the script): <x.y.z>
- Files parsed (3 or more): <Files parsed        : 3 of 3>
- Unresolved values line from the script: <paste>
- What it cannot give us: <for example references like aws_s3_bucket.data.id and module variables stay as text ${...}; dynamic blocks and count/for_each stay as expressions>
- Can it write HCL back? <the dict-to-HCL functions exist in version 8, but ARGUS does not need them: patches are applied to dictionaries and compiled to Terraform in Phase 7>
- Output : <File     : C:\Users\Prabhav\Downloads\ARGUS\ml\mutation_engine\fixtures\s3_bucket_good.tf
Result   : parsed OK   top-level blocks: resource
Resources: 4   distinct types: 4
           aws_s3_bucket                                           x1
           aws_s3_bucket_server_side_encryption_configuration      x1
           aws_s3_bucket_versioning                                x1
           aws_s3_bucket_public_access_block                       x1
Values   : 10 attribute values, 3 unresolved references (30%)
------------------------------------------------------------------------------
File     : C:\Users\Prabhav\Downloads\ARGUS\ml\mutation_engine\fixtures\security_group_good.tf    
Result   : parsed OK   top-level blocks: resource
Resources: 1   distinct types: 1
           aws_security_group                                      x1
Values   : 11 attribute values, 0 unresolved references (0%)
------------------------------------------------------------------------------
File     : C:\Users\Prabhav\Downloads\ARGUS\ml\real_data\samples\terraform-aws-s3-bucket_main.tf  
Result   : parsed OK   top-level blocks: data, locals, module, resource
Resources: 21   distinct types: 21
           aws_s3_bucket                                           x1
           aws_s3_directory_bucket                                 x1
           aws_s3_bucket_logging                                   x1
           aws_s3_bucket_acl                                       x1
           aws_s3_bucket_website_configuration                     x1
Values   : 271 attribute values, 270 unresolved references (100%)
Features : count in 17 resource(s), depends_on in 5 resource(s), dynamic in 11 resource(s), for_each in 4 resource(s), lifecycle in 1 resource(s)
==============================================================================
python-hcl2 version : 8.1.4
Files parsed        : 3 of 3
Resources found     : 26
Unresolved values   : 273 of 292 (93%)
Paste these lines into ml/real_data/SETUP_NOTES.md (HCL parser section).>

## 4. Problems found and what was done about them

- <one line each, or "none">

# Using MRI for Brain Tumor Detection and Segmentation
**Authors:** Isha Dev, Dharvi Jagirdar, Rohan Giridharan

This is the repository containing the code for the Machine Learning for Medical Applications Spring 2025 final project group working on: Using MRI for Brain Tumor Detection and Segmentation.

This work presents an Attention UNet model for brain tumor segmentation using the BraTS 2020 Challenge dataset. Using different MRI modalitied, out model leverages attention gates to enhance focus on tumor-relevant features and regions. A DDPM pipeline generates synthetic MRI data to augment UNet training for improved performance and generalization. Additionally, model outputs are passed to the Radiology Infer-Mini LLM to generate structured clinical reports to provide diagnostic and prognostic support, and increase interpretibility while aiming to reduce radiologist and physician cognitive load.

## Repo Guide
Data Handling
* `BraTS2020_Data_Handling.ipynb`: contains preliminary code from [Kaggle](https://www.kaggle.com/code/zeeshanlatif/brain-tumor-segmentation-using-u-net/notebook) to load and process the BraTS2020 Data
Models
* `Baseline_UNet.ipynb`: contains the implementation of the baseline UNet model derived from [Kaggle](https://www.kaggle.com/code/zeeshanlatif/brain-tumor-segmentation-using-u-net/notebook) with data processing, architecture and metric definition, model training and evaluation
  * The corresponding `Baseline_UNet` folder contains the saved model, training logs and data subset ids
* `AUNet.ipynb`: contains the implementation of the UNet model with attention with data processing, architecture and metric definision, model training, evaluation and segmentation characteristics collection to prepare LLM inputs
  * The corresponding `AUNet` folder contains the saved model, training logs, summarized segmentation outputs, T1ce and segmentation montages, structured LLM prompts, corresponding LLM outputs and similarity scores
* `AUNet_Synthetic.ipynb`: contains the implementation of the attention UNet model with added synthetic images during model training
  * The corresponding `AUNet_Synthetic` folder contains the saved model, training logs, summarized segmentation outputs, T1ce and segmentation montages, structured LLM prompts, corresponding LLM outputs and similarity scores
* `MRI_LLM.ipynb`: contains the implementation of `Radiology-Infer-Mini` vision language model along with the `all-MiniLM-L6-v2` model to create structured prompts, gather generated outputs for all test subjects for both the `AUNet` and `AUNet_Synthetic` models, and compute embedding similarity scores
* `DDPM.ipynb`: containes the implementation of the Denoising Diffusion Probabilistic Model (DDPM) along with generated synthetic images, and MM-SSIM evaluation computation

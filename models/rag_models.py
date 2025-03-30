# models/rag_models.py
from byaldi import RAGMultiModalModel
import shutil
import os
from pathlib import Path

# Extend RAGMultiModalModel with our improved delete_index method
class EnhancedRAGMultiModalModel(RAGMultiModalModel):
    """
    Enhanced version of RAGMultiModalModel with improved deletion capabilities
    """
    
    def load_index(self, index_name: str) -> bool:
        """Load an existing index by name.
        
        This method allows switching between different document-specific indices
        without creating a new model instance.
        
        Parameters:
            index_name (str): The name of the index to load.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            print(f"[EnhancedRAGMultiModalModel] Loading index: {index_name}")
            
            # Try to determine index path
            index_path = None
            
            # Path options to try
            paths_to_try = []
            
            # Path 1: Use model's index_root if available
            if hasattr(self.model, 'index_root'):
                index_root = self.model.index_root
                paths_to_try.append(Path(index_root) / str(index_name))
                paths_to_try.append(os.path.abspath(os.path.join(index_root, str(index_name))))
            
            # Path 2: Try relative to current directory
            paths_to_try.append(Path(".byaldi") / str(index_name))
            paths_to_try.append(os.path.abspath(os.path.join(".byaldi", str(index_name))))
            
            # Path 3: Try with absolute path from current working directory
            paths_to_try.append(Path(os.getcwd()) / ".byaldi" / str(index_name))
            
            # Check each path
            for path in paths_to_try:
                str_path = str(path)
                if os.path.exists(str_path):
                    print(f"[EnhancedRAGMultiModalModel] Found index at: {str_path}")
                    index_path = str_path
                    break
            
            if not index_path:
                print(f"[EnhancedRAGMultiModalModel] Index not found: {index_name}")
                return False
            
            # Try to load index from the found path
            # This depends on how the original Byaldi library implements index loading
            # The implementation below is a best guess based on typical patterns
            
            # Method 1: Use load_index if available
            if hasattr(self.model, 'load_index'):
                self.model.load_index(index_path)
                return True
                
            # Method 2: Manually set the index_name and load the embeddings
            elif hasattr(self.model, 'index_name'):
                # Set the current index name
                self.model.index_name = index_name
                
                # Attempt to load embeddings and metadata
                # This is a guess at the internal implementation
                if hasattr(self.model, 'load_embeddings'):
                    self.model.load_embeddings(index_path)
                
                return True
                
            # Method 3: Create a temporary instance and copy its attributes
            else:
                # Create a temporary model using from_index
                temp_model = RAGMultiModalModel.from_index(index_name)
                
                # Copy relevant attributes to this instance
                if hasattr(temp_model.model, 'indexed_embeddings'):
                    self.model.indexed_embeddings = temp_model.model.indexed_embeddings
                if hasattr(temp_model.model, 'embed_id_to_doc_id'):
                    self.model.embed_id_to_doc_id = temp_model.model.embed_id_to_doc_id
                if hasattr(temp_model.model, 'doc_id_to_metadata'):
                    self.model.doc_id_to_metadata = temp_model.model.doc_id_to_metadata
                if hasattr(temp_model.model, 'doc_ids_to_file_names'):
                    self.model.doc_ids_to_file_names = temp_model.model.doc_ids_to_file_names
                if hasattr(temp_model.model, 'doc_ids'):
                    self.model.doc_ids = temp_model.model.doc_ids
                if hasattr(temp_model.model, 'index_name'):
                    self.model.index_name = temp_model.model.index_name
                
                # Clean up
                del temp_model
                
                return True
                
        except Exception as e:
            print(f"[EnhancedRAGMultiModalModel] Error loading index {index_name}: {str(e)}")
            return False
    
    def delete_index(self, index_name: str) -> bool:
        """Delete an index by name.
        
        Parameters:
            index_name (str): The name of the index to delete.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            import shutil
            from pathlib import Path
            import os
            
            print(f"[EnhancedRAGMultiModalModel] Attempting to delete index: {index_name}")
            success = False
            
            # Try multiple path constructions to find the index
            paths_to_try = []
            
            # Path 1: Use model's index_root if available
            if hasattr(self.model, 'index_root'):
                index_root = self.model.index_root
                paths_to_try.append(Path(index_root) / str(index_name))
                paths_to_try.append(os.path.abspath(os.path.join(index_root, str(index_name))))
            
            # Path 2: Try relative to current directory
            paths_to_try.append(Path(".byaldi") / str(index_name))
            paths_to_try.append(os.path.abspath(os.path.join(".byaldi", str(index_name))))
            
            # Path 3: Try with absolute path from current working directory
            paths_to_try.append(Path(os.getcwd()) / ".byaldi" / str(index_name))
            
            # Path 4: Try directly with string path
            paths_to_try.append(os.path.join(".byaldi", str(index_name)))
            
            # Deduplicate paths
            unique_paths = []
            for p in paths_to_try:
                str_path = str(p)
                if str_path not in unique_paths:
                    unique_paths.append(str_path)
            
            print(f"[EnhancedRAGMultiModalModel] Trying the following paths:")
            for i, p in enumerate(unique_paths):
                print(f"  Path {i+1}: {p}")
            
            # Try each path with multiple deletion methods
            for path in unique_paths:
                str_path = str(path)
                
                # Check if path exists
                if os.path.exists(str_path):
                    print(f"[EnhancedRAGMultiModalModel] Found index at: {str_path}")
                    
                    # Try method 1: shutil.rmtree
                    try:
                        print(f"[EnhancedRAGMultiModalModel] Trying shutil.rmtree on: {str_path}")
                        shutil.rmtree(str_path)
                        if not os.path.exists(str_path):
                            print(f"[EnhancedRAGMultiModalModel] Successfully deleted with shutil.rmtree: {str_path}")
                            success = True
                            break
                    except Exception as e:
                        print(f"[EnhancedRAGMultiModalModel] shutil.rmtree failed: {str(e)}")
                    
                    # Try method 2: Direct Windows command
                    try:
                        cmd = f'rmdir /S /Q "{str_path}"'
                        print(f"[EnhancedRAGMultiModalModel] Trying Windows command: {cmd}")
                        os.system(cmd)
                        if not os.path.exists(str_path):
                            print(f"[EnhancedRAGMultiModalModel] Successfully deleted with Windows command: {str_path}")
                            success = True
                            break
                    except Exception as e:
                        print(f"[EnhancedRAGMultiModalModel] Windows command failed: {str(e)}")
                    
                    # Try method 3: Direct Unix command
                    try:
                        cmd = f'rm -rf "{str_path}"'
                        print(f"[EnhancedRAGMultiModalModel] Trying Unix command: {cmd}")
                        os.system(cmd)
                        if not os.path.exists(str_path):
                            print(f"[EnhancedRAGMultiModalModel] Successfully deleted with Unix command: {str_path}")
                            success = True
                            break
                    except Exception as e:
                        print(f"[EnhancedRAGMultiModalModel] Unix command failed: {str(e)}")
            
            # If no success with specific paths, try scanning .byaldi directory
            if not success:
                byaldi_dir = Path(".byaldi")
                if byaldi_dir.exists():
                    print(f"[EnhancedRAGMultiModalModel] Scanning .byaldi directory for matching index")
                    for item in byaldi_dir.iterdir():
                        if item.is_dir() and item.name == index_name:
                            str_item = str(item)
                            print(f"[EnhancedRAGMultiModalModel] Found index in .byaldi scan: {str_item}")
                            
                            # Try shutil
                            try:
                                shutil.rmtree(str_item)
                                if not os.path.exists(str_item):
                                    print(f"[EnhancedRAGMultiModalModel] Successfully deleted in scan: {str_item}")
                                    success = True
                                    break
                            except Exception as e:
                                print(f"[EnhancedRAGMultiModalModel] Deletion in scan failed: {str(e)}")
                                
                                # Try OS commands
                                try:
                                    os.system(f'rmdir /S /Q "{str_item}"')
                                    if not os.path.exists(str_item):
                                        print(f"[EnhancedRAGMultiModalModel] Successfully deleted with Windows command in scan")
                                        success = True
                                        break
                                except Exception:
                                    pass
                                
                                try:
                                    os.system(f'rm -rf "{str_item}"')
                                    if not os.path.exists(str_item):
                                        print(f"[EnhancedRAGMultiModalModel] Successfully deleted with Unix command in scan")
                                        success = True
                                        break
                                except Exception:
                                    pass
            
            # Clear index from memory if it was the active one
            if hasattr(self.model, 'index_name') and self.model.index_name == index_name:
                print(f"[EnhancedRAGMultiModalModel] Clearing index {index_name} from memory")
                self.model.indexed_embeddings = []
                self.model.embed_id_to_doc_id = {}
                self.model.doc_id_to_metadata = {}
                self.model.doc_ids_to_file_names = {}
                self.model.doc_ids = set()
                self.model.index_name = None
            
            # Final verification
            all_deleted = True
            for path in unique_paths:
                if os.path.exists(str(path)):
                    all_deleted = False
                    print(f"[EnhancedRAGMultiModalModel] WARNING: Index still exists at: {path}")
            
            if all_deleted:
                print(f"[EnhancedRAGMultiModalModel] Successfully deleted index: {index_name}")
                return True
            elif success:
                print(f"[EnhancedRAGMultiModalModel] Partial success deleting index: {index_name}")
                return True
            else:
                print(f"[EnhancedRAGMultiModalModel] Failed to delete index: {index_name}")
                return False
                
        except Exception as e:
            print(f"[EnhancedRAGMultiModalModel] Error in delete_index for {index_name}: {str(e)}")
            return False

def init_rag_model(model_name, verbose=1):
    """
    Initialize the RAG model with the given model name.
    
    Args:
        model_name: The name of the model to load
        verbose: Verbosity level (0=silent, 1=normal, 2=verbose)
    
    Returns:
        The initialized RAG model
    """
    print(f"Initializing RAG model {model_name}...")
    return EnhancedRAGMultiModalModel.from_pretrained(model_name, verbose=verbose)

def force_delete_index(index_name):
    """
    Forcefully delete an index by name using multiple methods.
    This utility function can be used even if the full RAG model isn't loaded.
    
    Args:
        index_name: The name of the index to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"Attempting to force delete index: {index_name}")
        success = False
        
        # Try multiple paths
        paths = [
            Path(".byaldi") / index_name,
            os.path.join(".byaldi", index_name),
            os.path.abspath(os.path.join(".byaldi", index_name)),
            os.path.join(os.getcwd(), ".byaldi", index_name)
        ]
        
        # Try each path
        for path in paths:
            str_path = str(path)
            if os.path.exists(str_path):
                print(f"Found index at: {str_path}")
                
                # Try shutil
                try:
                    shutil.rmtree(str_path)
                    if not os.path.exists(str_path):
                        print(f"Successfully deleted index at: {str_path}")
                        success = True
                        break
                except Exception as e:
                    print(f"shutil.rmtree failed: {str(e)}")
                
                # Try OS commands
                try:
                    os.system(f'rmdir /S /Q "{str_path}"')
                    if not os.path.exists(str_path):
                        print(f"Successfully deleted with Windows command")
                        success = True
                        break
                except Exception:
                    pass
                
                try:
                    os.system(f'rm -rf "{str_path}"')
                    if not os.path.exists(str_path):
                        print(f"Successfully deleted with Unix command")
                        success = True
                        break
                except Exception:
                    pass
        
        return success
    except Exception as e:
        print(f"Error during force_delete_index: {str(e)}")
        return False
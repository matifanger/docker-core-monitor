/**
 * Click outside directive
 * Calls the callback when a click occurs outside the node
 */
export function clickOutside(node: HTMLElement, callback: () => void) {
    function handleClick(event: MouseEvent) {
        if (node && !node.contains(event.target as Node) && !event.defaultPrevented) {
            callback();
        }
    }
    
    document.addEventListener('click', handleClick, true);
    
    return {
        destroy() {
            document.removeEventListener('click', handleClick, true);
        }
    };
}

/**
 * Draggable directive
 * Makes an element draggable and handles drag events
 */
export function draggable(node: HTMLElement, data: Record<string, unknown>) {
    let state = data;

    node.draggable = true;
    
    function handleDragStart(event: DragEvent) {
        if (!event.dataTransfer) return;
        
        if (typeof window.startDragging === 'function') {
            window.startDragging();
        }
        
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', JSON.stringify(state));
        
        node.classList.add('dragging');
        
        // Set a ghost image
        const ghost = node.cloneNode(true) as HTMLElement;
        ghost.style.position = 'absolute';
        ghost.style.top = '-1000px';
        ghost.style.opacity = '0.5';
        document.body.appendChild(ghost);
        event.dataTransfer.setDragImage(ghost, 0, 0);
        
        setTimeout(() => {
            document.body.removeChild(ghost);
        }, 0);
    }
    
    function handleDragEnd() {
        node.classList.remove('dragging');
        if (typeof window.stopDragging === 'function') {
            window.stopDragging();
        }
    }
    
    node.addEventListener('dragstart', handleDragStart);
    node.addEventListener('dragend', handleDragEnd);
    
    return {
        update(newState: Record<string, unknown>) {
            state = newState;
        },
        destroy() {
            node.removeEventListener('dragstart', handleDragStart);
            node.removeEventListener('dragend', handleDragEnd);
        }
    };
}

/**
 * Drop zone directive
 * Makes an element a drop zone for draggable elements
 */
export function dropZone(node: HTMLElement, options: { onDrop: (data: Record<string, unknown>) => void }) {
    function handleDragOver(event: DragEvent) {
        event.preventDefault();
        if (!event.dataTransfer) return;
        
        event.dataTransfer.dropEffect = 'move';
        node.classList.add('drop-target');
    }
    
    function handleDragEnter(event: DragEvent) {
        event.preventDefault();
        node.classList.add('drop-target');
    }
    
    function handleDragLeave() {
        node.classList.remove('drop-target');
    }
    
    function handleDrop(event: DragEvent) {
        event.preventDefault();
        node.classList.remove('drop-target');
        
        if (!event.dataTransfer) return;
        
        try {
            const data = JSON.parse(event.dataTransfer.getData('text/plain'));
            if (typeof window.startEditing === 'function') {
                window.startEditing(); // Prevent updates during the drop operation
            }
            options.onDrop(data);
            setTimeout(() => {
                if (typeof window.stopEditing === 'function') {
                    window.stopEditing();
                }
            }, 500); // Give time for the operation to complete
        } catch (e) {
            console.error('Error parsing drag data', e);
            if (typeof window.stopEditing === 'function') {
                window.stopEditing();
            }
        }
    }
    
    node.addEventListener('dragover', handleDragOver);
    node.addEventListener('dragenter', handleDragEnter);
    node.addEventListener('dragleave', handleDragLeave);
    node.addEventListener('drop', handleDrop);
    
    return {
        destroy() {
            node.removeEventListener('dragover', handleDragOver);
            node.removeEventListener('dragenter', handleDragEnter);
            node.removeEventListener('dragleave', handleDragLeave);
            node.removeEventListener('drop', handleDrop);
        }
    };
}

// Add global type definitions for the drag and drop functions
declare global {
    interface Window {
        startDragging?: () => void;
        stopDragging?: () => void;
        startEditing?: () => void;
        stopEditing?: () => void;
    }
} 